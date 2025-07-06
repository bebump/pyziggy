import unittest

from pyziggy.testing import MessageEvent


class TestMessageEvent(unittest.TestCase):
    def test_serialization(self):
        event_str = """
  0.14  RECV  zigbee2mqtt/dishwasher leak sensor  {
                                                    "battery": 97,
                                                    "identify": null,
                                                    "linkquality": 200,
                                                    "update": {
                                                      "installed_version": 16777223,
                                                      "latest_version": 16777223,
                                                      "state": "idle"
                                                    },
                                                    "water_leak": false
                                                  }
"""

        event = MessageEvent.from_str(event_str)[0]
        self.assertTrue(MessageEvent.from_str(str(event))[0] == event)

    concrete = MessageEvent.from_str(
        """
0.14  RECV  zigbee2mqtt/dishwasher leak sensor  {
                                                "battery": 97,
                                                "identify": null,
                                                "linkquality": 200,
                                                "update": {
                                                  "installed_version": 16777223,
                                                  "latest_version": 16777223,
                                                  "state": "idle"
                                                },
                                                "water_leak": true
                                              }
"""
    )[0]

    def test_simple_equality(self):
        generic_not_matching = MessageEvent.from_str(
            """
  0.14  RECV  zigbee2mqtt/dishwasher leak sensor  {
                                                    "battery": 97,
                                                    "identify": null,
                                                    "linkquality": 200,
                                                    "update": {
                                                      "installed_version": 16777223,
                                                      "latest_version": 16777223,
                                                      "state": "idle"
                                                    },
                                                    "water_leak": false
                                                  }
"""
        )[0]

        self.assertFalse(generic_not_matching.satisfied_by(TestMessageEvent.concrete))

        generic_matching = MessageEvent.from_str(
            """
  0.14  RECV  zigbee2mqtt/dishwasher leak sensor  {
                                                    "battery": 97,
                                                    "identify": null,
                                                    "linkquality": 200,
                                                    "update": {
                                                      "installed_version": 16777223,
                                                      "latest_version": 16777223,
                                                      "state": "idle"
                                                    },
                                                    "water_leak": true
                                                  }
"""
        )[0]

        self.assertTrue(generic_matching.satisfied_by(TestMessageEvent.concrete))

    def test_wildcard_value(self):
        generic_wildcard_value = MessageEvent.from_str(
            """
  0.14  RECV  zigbee2mqtt/dishwasher leak sensor  {
                                                "battery": 97,
                                                "identify": null,
                                                "linkquality": 200,
                                                "update": {
                                                  "installed_version": 16777223,
                                                  "latest_version": 16777223,
                                                  "state": "idle"
                                                },
                                                "water_leak": "*"
                                              }
"""
        )[0]

        self.assertTrue(generic_wildcard_value.satisfied_by(TestMessageEvent.concrete))

    def test_wildcard_member(self):
        generic_wildcard_member = MessageEvent.from_str(
            """
      0.14  RECV  zigbee2mqtt/dishwasher leak sensor  {
                                                    "battery": 97,
                                                    "identify": null,
                                                    "linkquality": 200,
                                                    "update": {
                                                      "installed_version": 16777223,
                                                      "latest_version": 16777223,
                                                      "state": "idle"
                                                    },
                                                    "*": "*"
                                                  }
    """
        )[0]

        self.assertTrue(generic_wildcard_member.satisfied_by(TestMessageEvent.concrete))


if __name__ == "__main__":
    unittest.main()
