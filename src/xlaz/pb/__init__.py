from tensorflow_checkpoint_reader.pb.tensorflow.compiler.xla.service import hlo_pb2
from tensorflow_checkpoint_reader.pb.tensorflow.compiler.xla import xla_pb2
from tensorflow_checkpoint_reader.pb.tensorflow.compiler.xla import xla_data_pb2

import sys as _sys

_sys.modules.update({
  k.replace('tensorflow_checkpoint_reader.pb.', __name__+'.'): v
  for k, v in _sys.modules.items()
  if k.startswith('tensorflow_checkpoint_reader.pb.')})

del _sys
