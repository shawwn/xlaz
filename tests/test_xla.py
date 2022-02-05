import unittest
import xla

class XlaTestCase(unittest.TestCase):
  def test_basic(self):
    self.assertEqual(1, 1)

if __name__ == '__main__':
  unittest.main()
