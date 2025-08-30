import time
import unittest

from pyziggy import message_loop as ml


class TestMessageLoopTimer(unittest.TestCase):
    def count_callbacks(self):
        num_a_callbacks = 0
        num_b_callbacks = 0

        one_of_the_timers_stopped = False

        def a(timer: ml.MessageLoopTimer):
            nonlocal num_a_callbacks, one_of_the_timers_stopped

            num_a_callbacks += 1

            if num_a_callbacks >= 4:
                timer.stop()

                if one_of_the_timers_stopped:
                    ml.message_loop.stop()

                one_of_the_timers_stopped = True
                return

        def b(timer: ml.MessageLoopTimer):
            nonlocal num_b_callbacks, one_of_the_timers_stopped

            num_b_callbacks += 1

            if num_b_callbacks >= 3:
                timer.stop()

                if one_of_the_timers_stopped:
                    ml.message_loop.stop()

                one_of_the_timers_stopped = True
                return

        timer_a = ml.MessageLoopTimer(a)
        timer_b = ml.MessageLoopTimer(b)

        timer_a.start(0.2)
        timer_b.start(0.4)

        ml.message_loop.run()

        return num_a_callbacks, num_b_callbacks

    def test_timer_basics(self):
        ml.time_source = ml.SystemTimeSource()

        start = time.perf_counter()
        num_a_callbacks, num_b_callbacks = self.count_callbacks()
        stop = time.perf_counter()

        self.assertTrue(num_a_callbacks == 4 and num_b_callbacks == 3)
        should_have_elapsed = max(0.2 * 5, 0.4 * 3)
        self.assertTrue(
            should_have_elapsed - 0.5 < stop - start < should_have_elapsed + 0.5,
            f"Elapsed time was {stop - start}, expected around {should_have_elapsed}",
        )

    def test_timer_can_be_fast_forwarded(self):
        ml.time_source = ml.FastForwardTimeSource()

        start = time.perf_counter()
        num_a_callbacks, num_b_callbacks = self.count_callbacks()
        stop = time.perf_counter()

        self.assertTrue(num_a_callbacks == 4 and num_b_callbacks == 3)
        self.assertTrue(stop - start < 0.2)


if __name__ == "__main__":
    unittest.main()
