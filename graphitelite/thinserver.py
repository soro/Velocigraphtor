import socket
import struct
import time
import bisect

from md5 import md5
from twisted.web import server, resource
from twisted.internet import reactor

try:
  import cPickle as pickle
except ImportError:
  import pickle

CARBONLINK_HOSTS = ['localhost:2003']
CARBONLINK_TIMEOUT = 100


#========================================
# Hashing

def hashRequest(request):
  # Normalize the request parameters so ensure we're deterministic
  queryParams = ["%s=%s" % (key, '&'.join(values))
                 for (key,values) in request.GET.lists()
                 if not key.startswith('_')]

  normalizedParams = ','.join( sorted(queryParams) ) or 'noParam'
  myHash = stripControlChars(normalizedParams) #memcached doesn't like unprintable characters in its keys

  if len(myHash) > 249: #memcached key size limitation
    return compactHash(myHash)
  else:
    return myHash


def hashData(targets, startTime, endTime):
  targetsString = ','.join(targets)
  startTimeString = startTime.strftime("%Y%m%d_%H%M")
  endTimeString = endTime.strftime("%Y%m%d_%H%M")
  myHash = targetsString + '@' + startTimeString + ':' + endTimeString
  myHash = stripControlChars(myHash)
  if len(myHash) > 249:
    return compactHash(myHash)
  else:
    return myHash


def stripControlChars(string):
  return filter(lambda char: ord(char) >= 33, string)


def compactHash(string):
  hash = md5()
  hash.update(string)
  return hash.hexdigest()



class ConsistentHashRing:
  def __init__(self, nodes, replica_count=100):
    self.ring = []
    self.replica_count = replica_count
    for node in nodes:
      self.add_node(node)

  def compute_ring_position(self, key):
    big_hash = md5( str(key) ).hexdigest()
    small_hash = int(big_hash[:4], 16)
    return small_hash

  def add_node(self, key):
    for i in range(self.replica_count):
      replica_key = "%s:%d" % (key, i)
      position = self.compute_ring_position(replica_key)
      entry = (position, key)
      bisect.insort(self.ring, entry)

  def remove_node(self, key):
    self.ring = [entry for entry in self.ring if entry[1] != key]

  def get_node(self, key):
    position = self.compute_ring_position(key)
    search_entry = (position, None)
    index = bisect.bisect_left(self.ring, search_entry)
    index %= len(self.ring)
    entry = self.ring[index]
    return entry[1]


#========================================
# data utils


class TimeSeries(list):
  def __init__(self, name, start, end, step, values, consolidate='average'):
    self.name = name
    self.start = start
    self.end = end
    self.step = step
    list.__init__(self,values)
    self.consolidationFunc = consolidate
    self.valuesPerPoint = 1
    self.options = {}


  def __iter__(self):
    if self.valuesPerPoint > 1:
      return self.__consolidatingGenerator( list.__iter__(self) )
    else:
      return list.__iter__(self)


  def consolidate(self, valuesPerPoint):
    self.valuesPerPoint = int(valuesPerPoint)


  def __consolidatingGenerator(self, gen):
    buf = []
    for x in gen:
      buf.append(x)
      if len(buf) == self.valuesPerPoint:
        while None in buf: buf.remove(None)
        if buf:
          yield self.__consolidate(buf)
          buf = []
        else:
          yield None
    while None in buf: buf.remove(None)
    if buf: yield self.__consolidate(buf)
    else: yield None
    raise StopIteration


  def __consolidate(self, values):
    usable = [v for v in values if v is not None]
    if not usable: return None
    if self.consolidationFunc == 'sum':
      return sum(usable)
    if self.consolidationFunc == 'average':
      return float(sum(usable)) / len(usable)
    raise Exception, "Invalid consolidation function!"


  def __repr__(self):
    return 'TimeSeries(name=%s, start=%s, end=%s, step=%s)' % (self.name, self.start, self.end, self.step)


  def getInfo(self):
    """Pickle-friendly representation of the series"""
    return {
      'name' : self.name,
      'start' : self.start,
      'end' : self.end,
      'step' : self.step,
      'values' : list(self),
    }

class CarbonLinkPool:
  def __init__(self, timeout):
    #parse hosts from local_settings.py
    hosts = []
    for host in CARBONLINK_HOSTS:
      parts = host.split(':')
      server = parts[0]
      port = int( parts[1] )
      if len(parts) > 2:
        instance = parts[2]
      else:
        instance = None

      hosts.append( (server, int(port), instance) )

    self.hosts = [ (server, instance) for (server, port, instance) in hosts ]
    self.ports = dict( ((server, instance), port) for (server, port, instance) in hosts )
    self.timeout = float(timeout)
    self.hash_ring = ConsistentHashRing(self.hosts)
    self.connections = {}
    self.last_failure = {}
    # Create a connection pool for each host
    for host in self.hosts:
      self.connections[host] = set()

  def select_host(self, metric):
    "Returns the carbon host that has data for the given metric"
    return self.hash_ring.get_node(metric)

  def get_connection(self, host):
    # First try to take one out of the pool for this host
    (server, instance) = host
    port = self.ports[host]
    connectionPool = self.connections[host]
    try:
      return connectionPool.pop()
    except KeyError:
      pass #nothing left in the pool, gotta make a new connection

    log.cache("CarbonLink creating a new socket for %s" % str(host))
    connection = socket.socket()
    connection.settimeout(self.timeout)
    try:
      connection.connect( (server, port) )
    except:
      self.last_failure[host] = time.time()
      raise
    else:
      connection.setsockopt( socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1 )
      return connection

  def query(self, metric):
    request = dict(type='cache-query', metric=metric)
    results = self.send_request(request)
    log.cache("CarbonLink cache-query request for %s returned %d datapoints" % (metric, len(results)))
    return results['datapoints']

  def get_metadata(self, metric, key):
    request = dict(type='get-metadata', metric=metric, key=key)
    results = self.send_request(request)
    log.cache("CarbonLink get-metadata request received for %s:%s" % (metric, key))
    return results['value']

  def set_metadata(self, metric, key, value):
    request = dict(type='set-metadata', metric=metric, key=key, value=value)
    results = self.send_request(request)
    log.cache("CarbonLink set-metadata request received for %s:%s" % (metric, key))
    return results

  def send_request(self, request):
    metric = request['metric']
    serialized_request = pickle.dumps(request, protocol=-1)
    len_prefix = struct.pack("!L", len(serialized_request))
    request_packet = len_prefix + serialized_request

    host = self.select_host(metric)
    conn = self.get_connection(host)
    try:
      conn.sendall(request_packet)
      result = self.recv_response(conn)
    except:
      self.last_failure[host] = time.time()
      raise
    else:
      self.connections[host].add(conn)
      if 'error' in result:
        raise CarbonLinkRequestError(result['error'])
      else:
        return result

  def recv_response(self, conn):
    len_prefix = recv_exactly(conn, 4)
    body_size = struct.unpack("!L", len_prefix)[0]
    body = recv_exactly(conn, body_size)
    return pickle.loads(body)

class CarbonLinkRequestError(Exception):
  pass

def recv_exactly(conn, num_bytes):
  buf = ''
  while len(buf) < num_bytes:
    data = conn.recv( num_bytes - len(buf) )
    if not data:
      raise Exception("Connection lost")
    buf += data

  return buf

#A shared importable singleton
CarbonLink = CarbonLinkPool(CARBONLINK_TIMEOUT)

def fetchData(request_args, pathExpr):
  if pathExpr.lower().startswith('graphite.'):
    pathExpr = pathExpr[9:]

  seriesList = []
  startTime = request_args['start'][0]
  endTime = request_args['end'][0]

  if request_args.get('localOnly'):
    store = LOCAL_STORE
  else:
    store = STORE

  for dbFile in store.find(pathExpr):
    print str(dbFile)
    log.metric_access(dbFile.metric_path)
    cachedResults = CarbonLink.query(dbFile.real_metric)
    dbResults = dbFile.fetch( timestamp(startTime), timestamp(endTime) )
    results = mergeResults(dbResults, cachedResults)

    if not results:
      continue

    (timeInfo,values) = results
    (start,end,step) = timeInfo
    series = TimeSeries(dbFile.metric_path, start, end, step, values)
    series.pathExpression = pathExpr #hack to pass expressions through to render functions
    seriesList.append(series)

  return seriesList

def mergeResults(dbResults, cacheResults):
  cacheResults = list(cacheResults)

  if not dbResults:
    return cacheResults
  elif not cacheResults:
    return dbResults

  (timeInfo,values) = dbResults
  (start,end,step) = timeInfo

  for (timestamp, value) in cacheResults:
    interval = timestamp - (timestamp % step)

    try:
      i = int(interval - start) / step
      values[i] = value
    except:
      pass

  return (timeInfo,values)

def timestamp(datetime):
  "Convert a datetime object into epoch time"
  return time.mktime( datetime.timetuple() )

class Simple(resource.Resource):
    isLeaf = True
    def render_GET(self, request):
        args = request.args
        start = args.get('start')[0]
        end = args.get('end')[0]
        # request.write("{'error' : 'must specify start and end'}")
        data = fetchData(args, '/Users/soeren/code/python/graphite/storage')
        request.write(str(data))
        # print request.received_headers
        # print request.args
        request.setHeader('Content-Type', 'application/json')

site = server.Site(Simple())
reactor.listenTCP(9000, site)
reactor.run()
