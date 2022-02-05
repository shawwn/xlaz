import unittest

import xlaz
import xlaz.hlo_lexer
from xlaz.pb.tensorflow.compiler.xla import xla_data_pb2, xla_pb2
from xlaz.pb.tensorflow.compiler.xla.service import hlo_pb2

class XlaTestCase(unittest.TestCase):
  def test_basic(self):
    self.assertEqual(1, 1)
    self.assertTrue(hlo_pb2.__name__.startswith('tensorflow_checkpoint_reader.'))
    self.assertTrue(xla_pb2.__name__.startswith('tensorflow_checkpoint_reader.'))
    self.assertTrue(xla_data_pb2.__name__.startswith('tensorflow_checkpoint_reader.'))

  def test_lexer(self):
    hlo_string = """
HloModule module
ENTRY %elementwise {
  %param0 = f32[5,7,11,13]{3,2,1,0} parameter(0),
    sharding={devices=[1,2,2,1]0,1,2,3},
    metadata={op_name="test"}
  ROOT %copy = f32[5,7,11,13]{3,2,1,0} copy(%param0)
}"""
    lexer = xlaz.hlo_lexer.HloLexer(hlo_string)
    loc = lexer.GetLoc()
    kind = lexer.GetKind()
    while True:
      was, kind = kind, lexer.Lex()
      prev, loc = loc, lexer.GetLoc()
      print(was, repr(prev.to(loc)))
      if prev == loc:
        break


if __name__ == '__main__':
  unittest.main()
