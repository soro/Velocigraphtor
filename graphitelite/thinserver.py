import socket
import struct
import time
import bisect
import inspect

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
            return "missing arguments"
        data = fetchData(args, '/Users/soeren/code/python/graphite/storage')
        request.setHeader('Content-Type', 'application/json')
        return str(data)

site = server.Site(Root())
reactor.listenTCP(9000, site)
reactor.run()


# import bottle
# from bottle import response, request, route, run

# @route('/metrics/:path')
# def show_metrics(path):
  # # This is really brittle; if you ask for something out of range of the files, it'll 500 :(
  # data = fetchData({'start': [int(request.params.get('start'))], 'end': [int(request.params.get('end'))]}, path)
  # response.content_type = "application/json"
  # return {"data": map(lambda datum: datum.getInfo(), data)}

# app = bottle.app()
# run(app, host='localhost', port=8080)
