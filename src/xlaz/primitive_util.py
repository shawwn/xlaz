from xlaz.pb.tensorflow.compiler.xla import xla_data_pb2 as xd
from functools import lru_cache

@lru_cache
def GetPrimitiveTypeStringMap():
  d = {k.lower(): v for k, v in xd.PrimitiveType.items() if v not in [xd.PRIMITIVE_TYPE_INVALID, xd.OPAQUE_TYPE]}
  d['opaque'] = xd.OPAQUE_TYPE
  return d

def StringToPrimitiveType(name) -> xd.PrimitiveType:
  return GetPrimitiveTypeStringMap()[str(name)]

def IsPrimitiveTypeName(name) -> bool:
  return str(name) in GetPrimitiveTypeStringMap()
