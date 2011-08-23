import socket
import struct
import time
import bisect
import inspect
import json

from md5 import md5
from twisted.web import server, resource
from twisted.internet import reactor

from graphitelite.data import TimeSeries, fetchData
from graphitelite.config import config
from graphitelite.log import log

try:
  import cPickle as pickle
except ImportError:
  import pickle

class Root(resource.Resource):
  isLeaf = True

  def render_GET(self, request):
    args = request.args
    try:
      path = args.get('path')[0]
      start = args.get('start')[0]
      end = args.get('end')[0]
    except:
      return "missing arguments, please set path, start and end"
    data = fetchData({'start': [int(start)], 'end': [int(end)]}, path)
    request.setHeader('Content-Type', 'application/json')
    response = '{"data": ' + json.dumps(map(lambda datum: datum.getInfo(), data)) + '}'
    return response

site = server.Site(Root())
reactor.listenTCP(9000, site)
reactor.run()
