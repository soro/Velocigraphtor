import socket
import struct
import time

from graphitelite.storage import STORE, LOCAL_STORE
from graphitelite.config import config
from graphitelite.hashing import ConsistentHashRing
from graphitelite.log import log

try:
  import cPickle as pickle
except ImportError:
  import pickle

CARBONLINK_HOSTS = config.get('main').get('carbon_link_hosts')
CARBONLINK_TIMEOUT = config.get('main').get('carbon_link_time_out')

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
    #parse hosts from app.json
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
    return results

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

def fetchPaths(metric):
  store = STORE
  return store.find(metric)

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
    log.metric_access(dbFile.metric_path)
    cachedResults = CarbonLink.query(dbFile.real_metric)
    dbResults = dbFile.fetch(startTime, endTime)
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
