import socket
import struct
import time
import bisect

from md5 import md5
from twisted.web import server, resource
from twisted.internet import reactor

from graphitelite.data import TimeSeries, fetchData
from graphitelite.config import config

try:
  import cPickle as pickle
except ImportError:
  import pickle

# class Simple(resource.Resource):
    # isLeaf = True
    # def render_GET(self, request):
        # args = request.args
        # start = args.get('start')[0]
        # end = args.get('end')[0]
        # # request.write("{'error' : 'must specify start and end'}")
        # data = fetchData(args, '/Users/soeren/code/python/graphite/storage')
        # request.write(str(data))
        # # print request.received_headers
        # # print request.args
        # request.setHeader('Content-Type', 'application/json')

# site = server.Site(Simple())
# reactor.listenTCP(9000, site)
# reactor.run()


import bottle
from bottle import route, run
from werkzeug.debug import DebuggedApplication

@route('/:start/:end')
def index(start='', end=''):
    data = fetchData({'start': [start], 'end': [end]}, '/Users/soeren/code/python/graphite/storage')
    return str(data)

app = bottle.app()
app.catchall = False #Now most exceptions are re-raised within bottle.
myapp = DebuggedApplication(app) #Replace this with a middleware of your choice (see below)
run(app=myapp, host='localhost', port=8080)
