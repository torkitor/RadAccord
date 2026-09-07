"""Executable image-transport witnesses and conditional radiomics relations.

Arrays use XYZ order. Affines map voxel centres to RAS coordinates in mm.
No image interpolation is performed by the representation transformations.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from itertools import permutations, product
from pathlib import Path
import hashlib
import numpy as np
import nibabel as nib

POSITION_ATOL_MM = 1e-4
INTENSITY_ATOL = 1e-4
FEATURE_RTOL = 1e-5
FEATURE_ATOL = 1e-6

@dataclass
class Frame:
    data: np.ndarray
    mask: np.ndarray
    affine: np.ndarray
    label: int = 1
    slope: float = 1.0
    intercept: float = 0.0

    def validate(self):
        if np.iscomplexobj(self.data) or np.iscomplexobj(self.mask):
            raise ValueError('Real-valued images and masks are required.')
        if self.data.ndim != 3 or self.mask.shape != self.data.shape:
            raise ValueError('A three-dimensional image and equally shaped mask are required.')
        if self.affine.shape != (4,4) or not np.all(np.isfinite(self.affine)):
            raise ValueError('A finite 4 by 4 affine is required.')
        if not np.array_equal(self.affine[3], [0.,0.,0.,1.]):
            raise ValueError('The affine homogeneous row is invalid.')
        if abs(np.linalg.det(self.affine[:3,:3])) < 1e-12:
            raise ValueError('The spatial affine is singular.')
        axes=self.affine[:3,:3]/np.linalg.norm(self.affine[:3,:3],axis=0)
        if not np.allclose(axes.T@axes,np.eye(3),atol=1e-6,rtol=0):
            raise ValueError('Only orthogonal voxel axes are supported; shear is outside the contract.')
        if isinstance(self.label,bool) or not isinstance(self.label,(int,np.integer)) or not 0<self.label<=32767:
            raise ValueError('The selected label must be a positive int16 integer.')
        if not np.all(np.isfinite(self.mask)) or not np.all(self.mask==self.mask.astype(np.int16)):
            raise ValueError('Mask values must be finite int16 integers.')
        if not np.all(np.isfinite(self.data)) or not np.any(self.mask == self.label):
            raise ValueError('Finite intensities and a nonempty selected label are required.')
        if not np.isfinite(self.slope) or self.slope <= 0 or not np.isfinite(self.intercept):
            raise ValueError('A positive finite encoding slope and finite intercept are required.')
        return self

    def payload(self):
        return {k:getattr(self,k).copy() if isinstance(getattr(self,k),np.ndarray) else getattr(self,k)
                for k in ('data','mask','affine','label','slope','intercept')}

def phantom(seed: int) -> Frame:
    """New asymmetric analytic fields, not sampled or derived from clinical data."""
    rng=np.random.default_rng(seed)
    shape=tuple(int(x) for x in rng.integers([25,27,23],[37,39,35]))
    ijk=np.indices(shape,dtype=float)
    centre=(np.asarray(shape)-1)/2+rng.uniform(-2,2,3)
    radii=np.asarray(shape)*rng.uniform(.22,.31,3)
    q=(ijk-centre[:,None,None,None])/radii[:,None,None,None]
    ell=np.sum(q*q,axis=0)<1
    lobe=((q[0]-.7)**2/.48**2+(q[1]+.25)**2/.58**2+(q[2]-.15)**2/.4**2)<1
    notch=(q[0]<-.4)&(q[1]>.15)&(q[2]>.1)
    mask=(ell|lobe)&~notch
    z=(125+18*q[0]+11*q[1]*q[2]+23*np.sin(2.4*q[0]+.3)*np.cos(3.1*q[1])
       +17*np.cos(3.7*q[2]+q[0])+rng.normal(0,3,shape))
    data=np.round(np.maximum(z,8)*4)/4
    angles=rng.uniform(.11,.63,3)
    ax,ay,az=angles;cx,cy,cz=np.cos(angles);sx,sy,sz=np.sin(angles)
    rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    spacing=rng.uniform([.65,1.1,2.0],[1.0,1.6,3.2])
    affine=np.eye(4);affine[:3,:3]=(rz@ry@rx)@np.diag(spacing)
    affine[:3,3]=rng.uniform([-70,-90,15],[-20,-25,65])
    return Frame(data,mask.astype(np.int16),affine).validate()

def reindex(frame: Frame, perm=(0,1,2), signs=(1,1,1)):
    if len(perm)!=3 or len(signs)!=3 or sorted(perm)!=[0,1,2] or any(v not in (-1,1) for v in signs):
        raise ValueError('An axis permutation and three unit signs are required.')
    b=np.zeros((4,4));b[3,3]=1
    for j,old in enumerate(perm):
        b[old,j]=signs[j]
        if signs[j]<0:b[old,3]=frame.data.shape[old]-1
    data=frame.data.transpose(perm);mask=frame.mask.transpose(perm)
    axes=tuple(j for j,s in enumerate(signs) if s<0)
    if axes:data=np.flip(data,axes);mask=np.flip(mask,axes)
    return replace(frame,data=data.copy(),mask=mask.copy(),affine=frame.affine@b),b

def orbit():
    return [(tuple(p),tuple(s)) for p in permutations(range(3)) for s in product((1,-1),repeat=3)]

def transform(frame: Frame, kind: str, **kwargs):
    """Return transformed data plus the declared index/world/intensity maps."""
    b=np.eye(4);l=np.eye(4);a=1.;offset=0.
    if kind=='reindex':out,b=reindex(frame,kwargs['perm'],kwargs['signs'])
    elif kind=='encoding':out=replace(frame,slope=kwargs['slope'],intercept=kwargs['intercept'])
    elif kind=='scale':
        scale=float(kwargs['scale']);l[:3,:3]*=scale
        if not np.isfinite(scale) or scale<=0:raise ValueError('Isotropic scale must be positive and finite.')
        out=replace(frame,affine=l@frame.affine)
    elif kind=='intensity':
        a=float(kwargs['gain']);offset=float(kwargs['offset'])
        if not np.isfinite(a) or a<=0 or not np.isfinite(offset):raise ValueError('Intensity gain must be positive and calibration finite.')
        out=replace(frame,data=a*frame.data+offset)
    elif kind=='label':
        label=int(kwargs['label']);out=replace(frame,mask=np.where(frame.mask==frame.label,label,0).astype(np.int16),label=label)
    else:raise ValueError(f'Unsupported transformation: {kind}')
    return out.validate(),{'kind':kind,'index_map':b.tolist(),'world_map':l.tolist(),
        'intensity_gain':a,'intensity_offset':offset,'parameters':kwargs}

def write_frame(frame: Frame, directory: Path, stem: str):
    frame.validate();directory.mkdir(parents=True,exist_ok=True)
    ip=directory/(stem+'_image.nii.gz');mp=directory/(stem+'_mask.nii.gz')
    raw=((frame.data-frame.intercept)/frame.slope).astype(np.float32)
    image=nib.Nifti1Image(raw,frame.affine)
    image.header.set_xyzt_units('mm');image.header.set_slope_inter(frame.slope,frame.intercept)
    image.set_sform(frame.affine,code=1);image.set_qform(frame.affine,code=1)
    mask=nib.Nifti1Image(frame.mask.astype(np.int16),frame.affine)
    mask.header.set_xyzt_units('mm');mask.set_sform(frame.affine,code=1);mask.set_qform(frame.affine,code=1)
    nib.save(image,ip);nib.save(mask,mp)
    return ip,mp

def read_frame(image_path: Path,mask_path: Path,label=1):
    image=nib.load(image_path);mask=nib.load(mask_path)
    for item in (image,mask):
        if item.header.get_xyzt_units()[0]!='mm':
            raise ValueError('Explicit millimetre spatial units are required.')
        q,qcode=item.get_qform(coded=True);s,scode=item.get_sform(coded=True)
        if qcode and scode and not np.allclose(q,s,atol=POSITION_ATOL_MM,rtol=0):
            raise ValueError('Conflicting qform and sform are outside the contract.')
    out=Frame(image.get_fdata(),np.asanyarray(mask.dataobj),image.affine,label).validate()
    geom={'same_shape':image.shape==mask.shape,'same_affine':bool(np.allclose(image.affine,mask.affine,atol=POSITION_ATOL_MM,rtol=0))}
    return out,geom

def transport_witness(source: Frame, observed: Frame, spec: dict):
    """Check the entire declared correspondence, not only a finite moment summary.

    The index map is restricted to a signed permutation and offset. Its validity
    is checked at all corner indices before corresponding arrays are compared.
    """
    b=np.asarray(spec['index_map']);l=np.asarray(spec['world_map'])
    if b.shape!=(4,4) or l.shape!=(4,4):raise ValueError('Invalid transform matrices.')
    if not np.all(np.isfinite(b)) or not np.all(np.isfinite(l)) or not np.array_equal(l[3],[0,0,0,1]):
        raise ValueError('Declared matrices must be finite affine transforms.')
    p=b[:3,:3]
    if not (np.all(np.isin(p,[-1,0,1])) and np.all(np.abs(p).sum(0)==1) and np.all(np.abs(p).sum(1)==1)):
        return {'status':'not_applicable','reason':'non-bijective index map'}
    perm=tuple(int(v) for v in np.argmax(np.abs(p),axis=0))
    if not np.array_equal(b[3],[0,0,0,1]) or not np.all(b[:3,3]==np.rint(b[:3,3])):
        return {'status':'not_applicable','reason':'nonintegral index translation or invalid homogeneous row'}
    expected_shape=tuple(source.data.shape[k] for k in perm)
    if expected_shape!=observed.data.shape:return {'status':'violated','reason':'shape mismatch'}
    # Independent of the transformation generator: evaluate i=Bj directly for
    # every destination voxel, then use those source indices as the oracle.
    indices=np.indices(expected_shape,dtype=np.int64).reshape(3,-1)
    mapped=(p.astype(np.int64)@indices+b[:3,3,None].astype(np.int64))
    if not np.array_equal(mapped.min(1),[0,0,0]) or not np.array_equal(mapped.max(1),np.asarray(source.data.shape)-1):
        return {'status':'not_applicable','reason':'index translation does not preserve the full grid'}
    source_indices=tuple(mapped[k] for k in range(3))
    corners=np.array(list(product(*[(0,n-1) for n in observed.data.shape])),float)
    homogeneous=np.column_stack([corners,np.ones(len(corners))])
    intended=(l@source.affine@b@homogeneous.T)[:3].T
    actual=(observed.affine@homogeneous.T)[:3].T
    pos=float(np.max(np.linalg.norm(intended-actual,axis=1)))
    target=source.data[source_indices].reshape(expected_shape)*spec['intensity_gain']+spec['intensity_offset']
    intensity=float(np.max(np.abs(target-observed.data)))
    roi=bool(np.array_equal((source.mask[source_indices]==source.label).reshape(expected_shape),observed.mask==observed.label))
    checks={'position':pos<=POSITION_ATOL_MM,'intensity':intensity<=INTENSITY_ATOL,'roi':roi}
    return {'status':'satisfied' if all(checks.values()) else 'violated','checks':checks,
            'max_corner_error_mm':pos,'max_intensity_error':intensity}

def analytic_anchors(frame: Frame):
    voxels=np.asarray(frame.data[frame.mask==frame.label],dtype=np.float64)
    return {'mean':float(voxels.mean()),'minimum':float(voxels.min()),'maximum':float(voxels.max()),
      'variance':float(voxels.var()),'energy':float(np.dot(voxels,voxels)),
      'voxel_volume':float(len(voxels)*abs(np.linalg.det(frame.affine[:3,:3]))),'n_voxels':int(len(voxels)),
      'full_rank_roi':bool(len(voxels)>3 and np.linalg.matrix_rank(np.cov(np.argwhere(frame.mask==frame.label).T))==3)}

def close(actual,expected):
    return bool(np.isfinite(actual) and np.isfinite(expected) and np.isclose(actual,expected,rtol=FEATURE_RTOL,atol=FEATURE_ATOL))

def frame_digest(frame: Frame):
    h=hashlib.sha256()
    for x in (frame.data.astype('<f8'),frame.mask.astype('<i2'),frame.affine.astype('<f8')):
        h.update(np.asarray(x.shape,dtype='<i8').tobytes());h.update(x.tobytes(order='C'))
    return h.hexdigest()
