"""Strict-mode and any-region gate tests (Session 7)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.region import validate_config, write_config_scaffold, RegionSpec
from engine.score import score_site
import json as _j

def main():
    # strict rejects provisional storm
    bad = {"region_id":"x","bounds":[0,0,1,1],"hydrology":{"design_storm_mm":150,"design_storm_status":"PROVISIONAL_UNVERIFIED","cn_table":{"vegetation":60,"impervious":98,"water":100,"bare":86}},"thermal":{"reference_c_status":"PENDING_SATELLITE","uhi_max_delta_status":"PENDING_DERIVATION","night_reference_status":"PENDING_SATELLITE","night_uhi_max_delta_status":"PENDING_DERIVATION"},"weights":{"flood":0.3,"heat":0.3,"green":0.2,"carbon":0.2},"green":{"green_weights_status":"HOUSE_JUDGMENT"},"carbon":{"bands_status":"UNSOURCED_BANDS","bands":[{"label":"Low","max":400}]},"epochs":{"scoring_supported":[2024]},"composite_weights_status":"HOUSE_POLICY"}
    try:
        validate_config(bad, strict=True)
        print("FAIL strict did not reject provisional")
        return 1
    except ValueError as e:
        print("PASS strict rejects provisional:", str(e)[:60])
    # non-strict accepts
    validate_config(bad, strict=False)
    print("PASS non-strict accepts")
    # synthetic scaffold labelled
    with tempfile.TemporaryDirectory() as tmp:
        p=os.path.join(tmp,"r.json")
        write_config_scaffold(RegionSpec(region_id="demo",display_name="Demo",bbox=[0,0,0.018,0.018]),p)
        cfg=json.load(open(p))
        assert cfg["hydrology"]["design_storm_status"]=="PROVISIONAL_UNVERIFIED"
        print("PASS scaffold provisional")
    return 0

if __name__=="__main__":
    raise SystemExit(main())