import socket
import struct
import time
import bisect

from md5 import md5
from twisted.web import server, resource
from twisted.internet import reactor

from graphitelite.config import config

try:
  import cPickle as pickle
except ImportError:
  import pickle

CARBONLINK_HOSTS = config.get('main', 'carbon_link_hosts')
CARBONLINK_TIMEOUT = config.get('main', 'carbon_link_time_out')

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
