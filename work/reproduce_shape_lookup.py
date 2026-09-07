"""Post hoc reconstruction from pinned upstream lookup tables; no native rerun.

Uses the downloaded v3.0.1 source tables only, checks four already-observed
orientation classes, and never changes a study input or frozen result.
"""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import SimpleITK as sitk

WORK = Path(__file__).resolve().parent
DIRECTORY = WORK/"heldout"
source_path = WORK/"pyradiomics_v3_0_1_cshape.c"
if hashlib.sha256(source_path.read_bytes()).hexdigest() != "e8d56aec5b7daa1777d97d91be942952949150c058eb817582ca80d37cd1f14e":
    raise ValueError("The user-supplied official v3.0.1 source does not match the archived SHA-256.")
source = source_path.read_text(encoding="utf-8")


def table(name):
    match = re.search(r"static const (?:int|double) " + name + r"(?:\[\d+\])+\s*=\s*(\{.*?\});", source, flags=re.S)
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", match.group(1), flags=re.S)
    return np.asarray(ast.literal_eval(text.replace("{", "[").replace("}", "]")))


angles, vertices, triangles = table("gridAngles"), table("vertList"), table("triTable")


def coefficients(mask, spacing):
    occupied = np.argwhere(mask)
    low, high = occupied.min(0), occupied.max(0)+1
    # Native featureextractor crops to ROI bounds, then shape pads one voxel.
    grid = np.pad(mask[tuple(slice(a,b) for a,b in zip(low,high))], 1)
    dims = np.asarray(grid.shape)-1
    codes = np.zeros(tuple(dims), np.uint8)
    for bit, offset in enumerate(angles):
        codes |= grid[tuple(slice(int(a),int(a+b)) for a,b in zip(offset,dims))].astype(np.uint8) << bit
    collected, signs, doubled = [], [], []
    for origin in np.argwhere((codes != 0) & (codes != 255)):
        code = int(codes[tuple(origin)])
        sign = -1 if code & 128 else 1
        if sign == -1:
            code ^= 255
        edge_ids = triangles[code]
        edge_ids = edge_ids[edge_ids >= 0].reshape(-1,3)
        positions = vertices[edge_ids] + origin
        collected.extend(positions*np.asarray(spacing))
        doubled.extend(np.rint(2*positions).astype(int))
        signs.extend([sign]*len(edge_ids))
    mesh = np.asarray(collected)
    v = np.einsum("ij,ij->i", np.cross(mesh[:,0], mesh[:,1]), mesh[:,2])/6
    area = np.linalg.norm(np.cross(mesh[:,0]-mesh[:,2],mesh[:,1]-mesh[:,2]),axis=1).sum()/2
    edges = Counter()
    for triangle in doubled:
        for a,b in ((0,1),(1,2),(2,0)):
            edges[tuple(sorted((tuple(triangle[a]),tuple(triangle[b]))))] += 1
    return {"volume": float(np.dot(v,np.asarray(signs))), "area": float(area), "triangles": len(mesh),
            "edge_use_counts": dict(Counter(edges.values())),
            "edges_not_used_exactly_twice": sum(count != 2 for count in edges.values())}


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


jobs = {row["job_id"]:row for row in read(DIRECTORY/"jobs.jsonl")}
outputs = {row["job_id"]:row for row in read(DIRECTORY/"pyradiomics.jsonl")}
first = outputs["1026_reference"]["features"]["original_shape_MeshVolume"]
representatives = {}
for index in range(48):
    job_id = f"1026_R{index:02d}"
    difference = round(outputs[job_id]["features"]["original_shape_MeshVolume"]-first, 6)
    representatives.setdefault(difference, job_id)
results = []
for job_id in representatives.values():
    job = jobs[job_id]
    image = sitk.ReadImage(str(DIRECTORY/job["image_path"]))
    mask_image = sitk.ReadImage(str(DIRECTORY/job["mask_path"]))
    mask = sitk.GetArrayFromImage(mask_image) == job["label"]
    reconstructed = coefficients(mask, image.GetSpacing()[::-1])
    native = outputs[job_id]["features"]
    expected = {"volume": native["original_shape_MeshVolume"], "area": native["original_shape_SurfaceArea"]}
    errors = {key: abs(reconstructed[key]-expected[key]) for key in expected}
    assert all(errors[key] <= 1e-9*max(1.0,abs(expected[key])) for key in expected)
    results.append({"job_id":job_id,"reconstructed":reconstructed,"native":expected,"absolute_error":errors})
report = {"post_hoc":True,"native_extraction_rerun":False,"frozen_results_modified":False,
          "upstream_source_url":"https://raw.githubusercontent.com/AIM-Harvard/pyradiomics/v3.0.1/radiomics/src/cshape.c",
          "upstream_source_sha256":hashlib.sha256(source_path.read_bytes()).hexdigest(),
          "lookup_reconstruction_matches_four_observed_orientation_classes":True,"cases":results}
(WORK/"shape_lookup_reconstruction.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
