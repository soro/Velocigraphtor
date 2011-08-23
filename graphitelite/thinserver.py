import socket
import struct
import time
import bisect
import inspect
import json

from md5 import md5
from twisted.web import server
from twisted.web.resource import Resource
from twisted.internet import reactor

from graphitelite.data import TimeSeries, fetchData, fetchPaths
from graphitelite.remote_storage import FindRequest
from graphitelite.config import config
from graphitelite.log import log

try:
  import cPickle as pickle
except ImportError:
  import pickle

class Root(Resource):
  isLeaf = False

  def getChild(self, name, request):
    if name == '':
      return self
    return Resource.getChild(self, name, request)

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

class Browse(Resource):
  isLeaf = True

  def render_GET(self, request):
    args = request.args
    try:
      metric = args.get('metric')[0]
    except:
      return "missing arguments, please set metric"
    paths = fetchPaths(metric)
    return json.dumps([{'metric': a.metric_path, 'isLeaf': a.isLeaf()} for a in paths])

root = Root()
root.putChild('browse', Browse())
site = server.Site(root)
reactor.listenTCP(9000, site)
reactor.run()
