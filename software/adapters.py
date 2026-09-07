"""Explicit native-engine adapters for a synthetic representation benchmark.

No filtering, normalisation or requested image resampling is performed. MIRP
uses its MR branch to preserve fractional synthetic intensities and native
fixed-bin-size anchoring at zero; its explicit nonnegative intensity range
excludes no voxel in this study's positive-valued phantoms. PyRadiomics uses
its own fixed-width discretisation. Cross-engine feature equality is not an
acceptance criterion. Native warnings and failures remain observable.

JSONL bridge (one persistent process per engine)::

    python adapters.py --engine pyradiomics --jobs jobs.jsonl --output out.jsonl
    python adapters.py --engine mirp --jobs jobs.jsonl --output out.jsonl
    python adapters.py --environment

Each job has job_id, image_path, mask_path and optional label/bin_width/
spatial_mode fields. Paths relative to the job file are supported. Outputs
contain native numeric feature names, timings, warnings and explicit failures;
they do not contain input paths or tracebacks. The module itself never decides
whether the caller should accept a representation.
"""
import argparse
from contextlib import redirect_stdout
from functools import lru_cache
import importlib.metadata
import json
import logging
import math
import os
from pathlib import Path
import platform
import sys
import time
import warnings


ENGINES = ("pyradiomics", "mirp")
PYRADIOMICS_AXIS_SPECIFIC = (
    "original_shape_Maximum2DDiameterSlice",
    "original_shape_Maximum2DDiameterColumn",
    "original_shape_Maximum2DDiameterRow",
)

# Isotropic spatial scaling f(a*x)=a**p*f(x). Unlisted features are not assigned
# a scale law here. Scalar invariance under valid signed axis permutations is a
# separate relation, with the three plane-specific diameters excluded.
SPATIAL_DEGREES = {
    "pyradiomics": {
        "original_shape_VoxelVolume": 3,
        "original_shape_MeshVolume": 3,
        "original_shape_SurfaceArea": 2,
        "original_shape_SurfaceVolumeRatio": -1,
        "original_shape_Maximum3DDiameter": 1,
        "original_shape_MajorAxisLength": 1,
        "original_shape_MinorAxisLength": 1,
        "original_shape_LeastAxisLength": 1,
        "original_shape_Elongation": 0,
        "original_shape_Flatness": 0,
        "original_shape_Sphericity": 0,
        "original_firstorder_TotalEnergy": 3,
    },
    "mirp": {
        "morph_volume": 3, "morph_vol_approx": 3, "morph_area_mesh": 2,
        "morph_av": -1, "morph_diam": 1, "morph_com": 1,
        "morph_pca_maj_axis": 1, "morph_pca_min_axis": 1,
        "morph_pca_least_axis": 1, "morph_integ_int": 3,
        "morph_comp_1": 0, "morph_comp_2": 0, "morph_sph_dispr": 0,
        "morph_sphericity": 0, "morph_asphericity": 0,
        "morph_pca_elongation": 0, "morph_pca_flatness": 0,
        "morph_vol_dens_conv_hull": 0, "morph_area_dens_conv_hull": 0,
        "morph_vol_dens_aabb": 0, "morph_area_dens_aabb": 0,
        "morph_vol_dens_aee": 0, "morph_area_dens_aee": 0,
        "morph_moran_i": 0, "morph_geary_c": 0,
    },
}

# These keys identify mathematical relations, not interchangeable definitions.
# Positive calibration slope a is required for quantile/min/max transport.
# Energy' = a^2 Energy + 2ab N Mean + b^2 N; variance' = a^2 variance.
# TotalEnergy is sum(x^2) multiplied by the volume of ONE voxel, not ROI volume.
INTENSITY_LAWS = {
    "pyradiomics": {
        "affine": ["original_firstorder_" + key for key in
                   ("Mean", "Minimum", "Maximum", "Median", "10Percentile", "90Percentile")],
        "variance": "original_firstorder_Variance",
        "energy": "original_firstorder_Energy",
        "mean": "original_firstorder_Mean",
        "voxel_volume": "original_shape_VoxelVolume",
    },
    "mirp": {
        "affine": ["stat_" + key for key in ("mean", "min", "max", "median", "p10", "p90")],
        "variance": "stat_var", "energy": "stat_energy", "mean": "stat_mean",
        "voxel_volume": "morph_vol_approx",
    },
}


@lru_cache(maxsize=16)
def _pyradiomics_extractor(bin_width):
    from radiomics import featureextractor
    extractor = featureextractor.RadiomicsFeatureExtractor(
        binWidth=bin_width, normalize=False, resampledPixelSpacing=None,
        correctMask=False, additionalInfo=False, force2D=False,
        voxelArrayShift=0, weightingNorm=None, symmetricalGLCM=True,
    )
    extractor.disableAllFeatures()
    for family in ("shape", "firstorder", "glcm", "glrlm"):
        extractor.enableFeatureClassByName(family)
    return extractor


def extract_features(engine, image_path, mask_path, label=1, bin_width=25.0, spatial_mode="3d"):
    """Return native feature keys mapped to floats; let native failures raise.

    This fixed study adapter accepts positive integer labels, three-dimensional
    input, and a positive finite bin width. MIRP's additional study domain is
    finite, nonnegative selected-ROI intensities. It deliberately performs no
    extra geometry validation: that is measured as a separate verifier/baseline.
    MIRP may register a mismatched mask according to its documented native policy.
    """
    if engine not in ENGINES:
        raise ValueError("engine must be pyradiomics or mirp")
    if spatial_mode != "3d":
        raise ValueError("This benchmark adapter only supports spatial_mode='3d'")
    if isinstance(label, bool) or not isinstance(label, int) or label <= 0:
        raise ValueError("label must be a positive integer")
    if not math.isfinite(float(bin_width)) or float(bin_width) <= 0:
        raise ValueError("bin_width must be positive and finite")
    if engine == "pyradiomics":
        result = _pyradiomics_extractor(float(bin_width)).execute(
            str(image_path), str(mask_path), label=label
        )
        return {str(key): float(value) for key, value in result.items()
                if str(key).startswith("original_")}

    import numpy as np
    import SimpleITK as sitk
    image_values = sitk.GetArrayFromImage(sitk.ReadImage(str(image_path)))
    mask_values = sitk.GetArrayFromImage(sitk.ReadImage(str(mask_path)))
    if image_values.shape == mask_values.shape:
        selected = image_values[mask_values == label]
        if selected.size and not np.all(np.isfinite(selected) & (selected >= 0)):
            raise ValueError("Selected ROI intensities are outside this MIRP adapter's finite nonnegative domain")
    from mirp import extract_features as extract_mirp
    result = extract_mirp(
        image=str(image_path), mask=str(mask_path), image_modality="mr", roi_name=str(label),
        base_feature_families=["morphology", "statistics", "glcm", "glrlm"],
        base_discretisation_method="fixed_bin_size", base_discretisation_bin_width=float(bin_width),
        glcm_spatial_method="3d_average", glrlm_spatial_method="3d_average",
        glcm_distance=1.0, new_spacing=None, by_slice=False, ibsi_compliant=True,
        intensity_normalisation="none", bias_field_correction=False,
        resegmentation_intensity_range=[0.0, float("nan")], no_approximation=True,
        export_features=True, write_features=False,
    )
    if not result or len(result) != 1 or result[0] is None or result[0].shape[0] != 1:
        raise RuntimeError("MIRP did not return exactly one feature row for the requested label")
    row = result[0].iloc[0]
    return {str(key): float(value) for key, value in row.items()
            if str(key).startswith(("morph_", "stat_", "cm_", "rlm_"))}


def environment_manifest():
    """Report actual installed versions without host names or local paths."""
    versions = {}
    for package in ("numpy", "scipy", "SimpleITK", "nibabel", "pandas", "scikit-image", *ENGINES):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {"python": platform.python_version(), "platform": platform.system(), "packages": versions,
            "thread_environment": {key: os.environ.get(key) for key in
                                   ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS")}}


def configure_worker_threads(threads=1):
    """Bound native threads before engine import; one process still runs one job.

    This is a worker resource policy, not a feature-definition setting. Call it
    before importing numerical libraries. The JSONL CLI does so by default.
    """
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ValueError("threads must be a positive integer")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"):
        os.environ[key] = str(threads)
    import SimpleITK as sitk
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(threads)


def _safe_message(message, input_paths):
    text = str(message)
    for path in input_paths:
        for part in (str(path), str(path.parent)):
            variants = (part, part.replace("\\", "/"), part.replace("/", "\\"),
                        part.replace("\\", "\\\\"))
            for variant in sorted(set(variants), key=len, reverse=True):
                text = text.replace(variant, "<INPUT>")
    return text


def run_jobs(engine, jobs_path, output_path):
    jobs_path, output_path = Path(jobs_path).resolve(), Path(output_path).resolve()
    if jobs_path == output_path:
        raise ValueError("The output must not overwrite the input job file")
    seen = set()
    with jobs_path.open(encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            job = json.loads(line)
            job_id = job["job_id"]
            if job_id in seen:
                raise ValueError(f"Duplicate job_id at line {line_number}")
            seen.add(job_id)
            image_path, mask_path = (Path(job[key]) for key in ("image_path", "mask_path"))
            image_path = image_path if image_path.is_absolute() else jobs_path.parent / image_path
            mask_path = mask_path if mask_path.is_absolute() else jobs_path.parent / mask_path
            settings = {key: job[key] for key in ("label", "bin_width", "spatial_mode") if key in job}
            record = {"job_id": job_id, "engine": engine, "settings": settings}
            started = time.perf_counter()
            logged = []

            class WarningCollector(logging.Handler):
                def emit(self, item):
                    logged.append({"category": "Logging" + item.levelname,
                                   "message": _safe_message(item.getMessage(), (image_path, mask_path))})

            collector = WarningCollector(level=logging.WARNING)
            logging.getLogger().addHandler(collector)
            with warnings.catch_warnings(record=True) as observed:
                warnings.simplefilter("always", UserWarning)
                try:
                    # Library stdout can contain progress. Keep JSONL output separate.
                    with redirect_stdout(sys.stderr):
                        features = extract_features(engine, image_path, mask_path, **settings)
                    nonfinite = [key for key, value in features.items() if not math.isfinite(value)]
                    record.update(status="extracted", feature_count=len(features),
                                  features={key: value if math.isfinite(value) else None
                                            for key, value in features.items()},
                                  nonfinite_features=nonfinite)
                except Exception as error:
                    record.update(status="failed", error_type=type(error).__name__,
                                  error=_safe_message(error, (image_path, mask_path)))
                finally:
                    logging.getLogger().removeHandler(collector)
            record["seconds"] = time.perf_counter() - started
            record["warnings"] = [
                {"category": item.category.__name__,
                 "message": _safe_message(item.message, (image_path, mask_path))}
                for item in observed
            ] + logged
            target.write(json.dumps(record, allow_nan=False, sort_keys=True) + "\n")
            target.flush()
    return len(seen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=ENGINES)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--environment", action="store_true")
    parser.add_argument("--threads", type=int, default=1,
                        help="Native threads per worker; set before engine import (default: 1)")
    args = parser.parse_args()
    if args.environment:
        print(json.dumps(environment_manifest(), indent=2))
    elif args.engine and args.jobs and args.output:
        configure_worker_threads(args.threads)
        print(json.dumps({"completed_jobs": run_jobs(args.engine, args.jobs, args.output)}))
    else:
        parser.error("provide --environment or --engine, --jobs and --output")
