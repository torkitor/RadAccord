"""Command-line entry point for the revised physical-consistency profile."""
from pathlib import Path
import argparse,json,sys
from verify import verify
from validation_refinement import revised_report
from benchmark import dump

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-image','source-mask','candidate-image','candidate-mask','contract','engine-python','report'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--engine',choices=('pyradiomics','mirp'),required=True);a=p.parse_args()
    try:
        contract=json.loads(a.contract.read_text(encoding='utf-8'))
        report=revised_report(verify(a.source_image,a.source_mask,a.candidate_image,a.candidate_mask,contract,a.engine,a.engine_python),contract['transformation']['kind'])
        dump(a.report,report);print(report['decision']);sys.exit(1 if report['decision']=='violated' else 2 if report['decision']=='not_applicable' else 0)
    except Exception as e:
        dump(a.report,{'decision':'unavailable','error_type':type(e).__name__,'reason':'Supported input, contract or extraction unavailable.'})
        print('unavailable');sys.exit(2)
