"""Conditional scalar relations; no cross-engine equality is asserted."""
import math
import json
from pathlib import Path
from adapters import SPATIAL_DEGREES, INTENSITY_LAWS, PYRADIOMICS_AXIS_SPECIFIC
from physical_contracts import close


def schema_check(engine,features,bin_width=25.):
    """The released protocol requires the complete pinned native output schema."""
    path=Path(__file__).with_name('protocol')/'feature_schema.json'
    if not path.exists():return {'status':'unavailable','reason':'frozen output schema is absent'}
    required=set(json.loads(path.read_text(encoding='utf-8'))[engine]);actual=set(features)
    if engine=='mirp':required={k.replace('_fbs_w25.0',f'_fbs_w{float(bin_width)}') for k in required}
    return {'status':'satisfied' if required==actual else 'violated',
            'missing':sorted(required-actual),'unexpected':sorted(actual-required)}


def _decision(actual, expected):
    if actual is None or expected is None or not math.isfinite(actual) or not math.isfinite(expected):
        return {'status':'violated','reason':'missing or nonfinite required value'}
    return {'status':'satisfied' if close(actual,expected) else 'violated',
            'actual':actual,'expected':expected,'absolute_error':abs(actual-expected),
            'scaled_error':abs(actual-expected)/max(1.,abs(expected))}


def summarize(decisions):
    counts={s:sum(x['status']==s for x in decisions.values()) for s in ('satisfied','violated','not_applicable')}
    status='violated' if counts['violated'] else ('satisfied' if counts['satisfied'] else 'not_applicable')
    return {'status':status,'counts':counts,'features':decisions}


def compare_features(engine, reference, observed, spec, n_voxels, settings_equal=True, domain=None):
    """Apply only declared laws in the native unfiltered 3D adapter context.

    A changed extraction configuration abstains from the full-vector relation.
    Unassigned scale/calibration laws and plane-specific diameters also abstain.
    Missing required outputs fail; abstention never counts as a passed feature.
    """
    decisions={};laws=INTENSITY_LAWS[engine];kind=spec['kind']
    if kind not in ('reindex','encoding','label','identity','scale','intensity'):
        settings_equal=False
    for key,value in reference.items():
        reason=None;expected=None
        if not settings_equal:reason='configuration or transformation outside this relation'
        elif engine=='mirp' and key in ('morph_com','morph_moran_i','morph_geary_c','morph_vol_dens_aee','morph_area_dens_aee') and domain is None:
            reason='independent input domain information is unavailable'
        elif engine=='mirp' and key=='morph_com' and domain['mean']==0:
            reason='intensity-weighted centre requires a nonzero ROI intensity sum'
        elif engine=='mirp' and key in ('morph_moran_i','morph_geary_c') and (domain['n_voxels']<2 or domain['variance']<=0):
            reason='spatial autocorrelation requires at least two nonconstant voxels'
        elif engine=='mirp' and key in ('morph_vol_dens_aee','morph_area_dens_aee') and not domain['full_rank_roi']:
            reason='ellipsoid densities require three positive semiaxes'
        elif engine=='mirp' and key in ('morph_max_2d_diam_z','morph_max_2d_diam_y','morph_max_2d_diam_x'):
            reason='plane-specific output requires an axis-labelled relation'
        elif engine=='pyradiomics' and key in PYRADIOMICS_AXIS_SPECIFIC:
            reason='plane-specific output requires an axis-labelled relation'
        elif kind in ('reindex','encoding','label','identity'):expected=value
        elif kind=='scale':
            degree=SPATIAL_DEGREES[engine].get(key)
            if degree is None:reason='no assigned isotropic spatial degree'
            else:expected=value*spec['parameters']['scale']**degree if value is not None else None
        elif kind=='intensity':
            a=spec['intensity_gain'];b=spec['intensity_offset']
            if a<=0:reason='positive gain required'
            elif key in laws['affine']:expected=a*value+b if value is not None else None
            elif key==laws['variance']:expected=a*a*value if value is not None else None
            elif key==laws['energy']:
                mean=reference.get(laws['mean'])
                expected=a*a*value+2*a*b*n_voxels*mean+b*b*n_voxels if value is not None and mean is not None else None
            else:reason='no assigned intensity calibration law'
        decisions[key]={'status':'not_applicable','reason':reason} if reason else _decision(observed.get(key),expected)
    if not decisions:return {'status':'violated','counts':{},'features':{},'reason':'empty reference output'}
    return summarize(decisions)


def check_anchors(engine,features,anchors):
    laws=INTENSITY_LAWS[engine]
    suffix={'mean':'Mean','minimum':'Minimum','maximum':'Maximum','variance':'Variance','energy':'Energy'}
    mapping={a:'original_firstorder_'+b for a,b in suffix.items()} if engine=='pyradiomics' else {
        'mean':'stat_mean','minimum':'stat_min','maximum':'stat_max','variance':'stat_var','energy':'stat_energy'}
    mapping['voxel_volume']=laws['voxel_volume']
    return summarize({key:_decision(features.get(key),anchors[anchor]) for anchor,key in mapping.items()})
