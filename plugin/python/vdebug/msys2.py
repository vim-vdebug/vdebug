import vdebug.opts
import platform

def shell():
    return platform.system()[:4] == 'MSYS'

def toNativePath(path):
    return path[1].upper() + ':' + path[2:].replace('/','\\')

def toMSYSPath(path):
    return '/' + path[0].lower() + path[2:].replace('\\','/')
