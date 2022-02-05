import unittest
import xlaz
from xlaz.pb.tensorflow.compiler.xla import xla_pb2
from xlaz.pb.tensorflow.compiler.xla import xla_data_pb2
from xlaz.pb.tensorflow.compiler.xla.service import hlo_pb2
print(hlo_pb2)

class XlaTestCase(unittest.TestCase):
  def test_basic(self):
    self.assertEqual(1, 1)
    self.assertTrue(hlo_pb2.__name__.startswith('tensorflow_checkpoint_reader.'))
    self.assertTrue(xla_pb2.__name__.startswith('tensorflow_checkpoint_reader.'))
    self.assertTrue(xla_data_pb2.__name__.startswith('tensorflow_checkpoint_reader.'))

if __name__ == '__main__':
  unittest.main()
