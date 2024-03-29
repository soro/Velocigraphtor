import bisect
from md5 import md5

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

