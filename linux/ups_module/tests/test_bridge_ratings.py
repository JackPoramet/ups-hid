"""Ensure unknown watt ratings are not fabricated for Unity variants."""
import unittest
import enerex_ups_bridge as bridge

class RatingTests(unittest.TestCase):
    def test_unity_1k_does_not_inherit_3k_watts(self):
        data={'ups.status':'OL','ups.power.nominal':1000,'ups.load':50,'output.voltage':230}
        result=bridge.enrich_nut_variables(data,{'model':'Innova Unity','model_sub':'Tower 1K'})
        self.assertNotIn('ups.realpower.nominal',result)
        self.assertNotIn('output.power',result)

    def test_explicit_10k_keeps_its_known_rating(self):
        result=bridge.enrich_nut_variables({'ups.status':'OL'},{'model':'Innova Unity','model_sub':'Tower 3-1 10K'})
        self.assertEqual(result['ups.realpower.nominal'],9000)

if __name__=='__main__':unittest.main()
