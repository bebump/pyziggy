import unittest

from pyziggy.message_loop import MessageLoopTimer
from pyziggy.util import Barriers


class TestBarriers(unittest.TestCase):
    def test_barriers(self):
        timer = MessageLoopTimer(lambda x: None)

        b = Barriers([0.2, 0.5, 0.8])

        def reset_timer():
            b._reset(timer)

        def apply_value(val):
            return b.apply(val)

        self.assertTrue(apply_value(0.1) == 0.1)
        self.assertTrue(apply_value(0.3) == 0.2)
        reset_timer()
        self.assertTrue(apply_value(0.6) == 0.5)
        self.assertTrue(apply_value(0.0) == 0.2)
        self.assertTrue(apply_value(1.0) == 0.5)
        reset_timer()
        self.assertTrue(apply_value(0.75) == 0.75)
        self.assertTrue(apply_value(0.48) == 0.5)
        reset_timer()
        self.assertTrue(apply_value(0.4) == 0.4)
        apply_value(0.51)
        reset_timer()
        apply_value(0.0)
        reset_timer()
        apply_value(0.0)
        apply_value(0.25)
        reset_timer()
        apply_value(0.52)
        reset_timer()
        apply_value(0.1)

        b = Barriers([0.55, 0.94])
        self.assertTrue(apply_value(0) == 0)
        self.assertTrue(apply_value(0.6) == 0.55)
        reset_timer()
        self.assertTrue(apply_value(0.96) == 0.94)
        reset_timer()
        self.assertTrue(apply_value(0.83) == 0.83)
        self.assertTrue(apply_value(0.2) == 0.55)


if __name__ == "__main__":
    unittest.main()
