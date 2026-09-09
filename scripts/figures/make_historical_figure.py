"""Historical native NIfTI geometry reproduction from archived numerical records.

No images are decoded or clinical/held-out extraction is run by this builder.
Run from any directory with --output for the desired publication destination.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
from itertools import product
import json

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[2]
style_spec = importlib.util.spec_from_file_location('radaccord_publication_style', ROOT/'work/figure_style.py')
style = importlib.util.module_from_spec(style_spec)
style_spec.loader.exec_module(style)


def physical(indices, affine):
    return np.asarray(indices) @ np.asarray(affine)[:3, :3].T + np.asarray(affine)[:3, 3]


def grid(ax, affine, shape, origin, color, linewidth, linestyle='-'):
    corners = np.asarray(list(product(*[(0, n-1) for n in shape])), dtype=float)
    points = physical(corners, affine)-origin
    # Twelve physical edges and a sparse central index plane are enough to show
    # orientation without inventing a decorative image or altering geometry.
    for i, first in enumerate(corners):
        for j in range(i+1, len(corners)):
            if np.count_nonzero(first != corners[j]) == 1:
                ax.plot(*points[[i, j]].T, color=color, lw=linewidth, ls=linestyle)
    for axis in (0, 1):
        for coordinate in np.linspace(0, shape[axis]-1, 5)[1:-1]:
            index = np.zeros((2, 3))
            index[:, 2] = (shape[2]-1)/2
            index[:, axis] = coordinate
            index[:, 1-axis] = [0, shape[1-axis]-1]
            ax.plot(*(physical(index, affine)-origin).T, color=color, lw=linewidth*.7,
                    ls=linestyle, alpha=.65)
    return points


def build(results, output):
    style.configure()
    versions = ('2.4.1', '2.4.2')
    records = {v: json.loads((results/(v+'.json')).read_text(encoding='utf-8')) for v in versions}
    ids = ('axis_aligned', 'oblique_z', 'oblique_xyz')
    cases = {v: {case['case_id']: case for case in records[v]['cases']} for v in versions}
    plotted = []
    for version in versions:
        assert set(cases[version]) == set(ids)
        for case_id in ids:
            case = cases[version][case_id]
            corners = np.asarray(list(product(*[(0, n-1) for n in case['shape']])), dtype=float)
            error = float(np.linalg.norm(physical(corners, case['exported_affine_ras_mm'])-
                                         physical(corners, case['source_affine_ras_mm']), axis=1).max())
            np.testing.assert_allclose(error, case['verification']['max_corner_error_mm'], rtol=0, atol=1e-12)
            assert case['array_exact'] and case['mask_exact'] and case['paired_export_geometry_agrees']
            plotted.append({'version': version, 'case_id': case_id, 'max_corner_error_mm': error,
                            'array_exact': True, 'mask_exact': True, 'paired_export_geometry_agrees': True})

    fig = plt.figure(figsize=(6.5, 4.7))
    fig.text(.035, .955, 'a', fontsize=11, weight='bold')
    fig.text(.077, .955, 'Oblique source and native export', fontsize=9.5)
    fig.text(.545, .955, 'b', fontsize=11, weight='bold')
    fig.text(.587, .955, 'Source-referenced physical error', fontsize=9.5)
    fig.text(.035, .90, 'Source NIfTI  →  MIRP read / write  →  Exported NIfTI', fontsize=8.3,
             color=style.GREY)

    ax = fig.add_axes([.010, .365, .48, .47], projection='3d')
    older = cases['2.4.1']['oblique_xyz']
    newer = cases['2.4.2']['oblique_xyz']
    origin = np.asarray(older['source_affine_ras_mm'])[:3, 3]
    source_points = grid(ax, older['source_affine_ras_mm'], older['shape'], origin, style.BLUE, 1.05)
    updated_points = grid(ax, newer['exported_affine_ras_mm'], newer['shape'], origin, style.BLUE, .65, '--')
    old_points = grid(ax, older['exported_affine_ras_mm'], older['shape'], origin, style.RED, 1.05)
    corner = np.argmax(np.linalg.norm(old_points-source_points, axis=1))
    ax.plot(*np.stack((source_points[corner], old_points[corner])).T, color=style.GREY,
            lw=1.15, ls=(0, (2, 2)))
    ax.scatter(*source_points[corner], s=11, color=style.BLUE, depthshade=False)
    ax.scatter(*old_points[corner], s=11, color=style.RED, depthshade=False)
    all_points = np.vstack((source_points, old_points, updated_points))
    low, high = all_points.min(axis=0), all_points.max(axis=0)
    for set_limits, a, b in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), low, high):
        set_limits(a-1., b+1.)
    ax.set_box_aspect(high-low)
    ax.set_proj_type('ortho')
    ax.view_init(elev=23, azim=-57)
    ax.set_xlabel('R (mm)', fontsize=8, labelpad=-1)
    ax.set_ylabel('A (mm)', fontsize=8, labelpad=-1)
    ax.set_zlabel('')
    ax.text2D(.91, .83, 'S (mm)', transform=ax.transAxes, fontsize=8, ha='center')
    ax.tick_params(axis='both', labelsize=8, pad=-1)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_pane_color((1, 1, 1, 0))
        axis._axinfo['grid']['color'] = (.85, .85, .85, .5)
        axis._axinfo['grid']['linewidth'] = .35
        axis.line.set_color(style.LINE)
    ax.set_xticks([0, 10, 20]); ax.set_yticks([0, 10, 20]); ax.set_zticks([0, 10, 20])
    fig.text(.035, .285, 'Three-axis oblique example: 11.12 mm maximum', fontsize=8.2)
    fig.text(.035, .250, 'Coordinates relative to the declared source origin', fontsize=8, color=style.GREY)
    fig.legend(handles=[Line2D([0], [0], color=style.BLUE, lw=1.4, label='Source / 2.4.2 (overlap)'),
                        Line2D([0], [0], color=style.RED, lw=1.4, label='MIRP 2.4.1 export')],
               loc='lower left', bbox_to_anchor=(.02, .151), frameon=False, fontsize=8, handlelength=2)

    chart = fig.add_axes([.625, .365, .34, .475])
    chart.set_yscale('log')
    chart.set_ylim(2e-7, 60)
    chart.set_xlim(-.45, 2.48)
    chart.axhspan(2e-7, 1e-4, color=style.PALE, zorder=0)
    chart.axhline(1e-4, color=style.GREY, lw=.8, ls=(0, (4, 3)), zorder=1)
    chart.text(-.38, 1.6e-4, 'Tolerance 0.0001 mm', fontsize=8, color=style.GREY)
    for i, case_id in enumerate(ids):
        values = [next(row['max_corner_error_mm'] for row in plotted
                       if row['version']==version and row['case_id']==case_id) for version in versions]
        chart.plot([i-.1, i+.1], values, color=style.LINE, lw=1, zorder=2)
        for offset, value, color, marker in zip((-.1, .1), values,
                                               (style.RED, style.BLUE), ('o', 's')):
            chart.scatter(i+offset, value, s=34, color=color, marker=marker,
                          edgecolors='white', linewidths=.55, zorder=3)
        if i:
            chart.text(i-.10, values[0]*1.48, f'{values[0]:.2f}', ha='center', fontsize=8.2,
                       color=style.RED_TEXT)
    chart.set_yticks([1e-6, 1e-4, 1e-2, 1, 10])
    chart.set_yticklabels(['0.000001', '0.0001', '0.01', '1', '10'])
    chart.minorticks_off()
    chart.tick_params(axis='x', length=0, pad=7)
    chart.set_xticks(range(3), ['Axis\naligned', 'Oblique\nz', 'Oblique\nx, y, z'], fontsize=8.2)
    chart.set_ylabel('Maximum corner displacement (mm)', fontsize=8.3, labelpad=6)
    chart.spines['bottom'].set_visible(False)
    chart.legend(handles=[Line2D([0], [0], color=style.RED, marker='o', ls='None', markersize=5, label='2.4.1'),
                          Line2D([0], [0], color=style.BLUE, marker='s', ls='None', markersize=5, label='2.4.2')],
                 title='MIRP version', title_fontsize=8, fontsize=8, frameon=False,
                 loc='upper left', bbox_to_anchor=(.03, .98), handletextpad=.45)
    fig.text(.605, .235, 'Three cases × two native versions', fontsize=8, color=style.GREY)
    fig.text(.605, .197, '2.4.2: all errors < 0.000003 mm', fontsize=8.2, color=style.BLUE)

    fig.add_artist(Line2D([.035, .965], [.132, .132], transform=fig.transFigure, color=style.LINE, lw=.7))
    fig.text(.035, .095, 'Exact image arrays: 6/6     Exact ROI masks: 6/6     Paired export geometry equal: 6/6', fontsize=8.1)
    fig.text(.035, .047, 'Targeted retrospective reproduction · NIfTI read–write boundary · Feature effects not tested',
             fontsize=8, color=style.GREY)
    style.export_figure(fig, output, 'P2_Fig3')
    plt.close(fig)
    audit = {'source_sha256': {version+'.json': hashlib.sha256((results/(version+'.json')).read_bytes()).hexdigest()
                               for version in versions}, 'values': plotted,
             'displayed_geometry_case': 'oblique_xyz', 'position_tolerance_mm': 1e-4,
             'scope': 'Historical synthetic native NIfTI read-write only; no feature effects measured.'}
    (output/'P2_Fig3_values.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT/'results/mirp_nifti_regression')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/figures/native')
    arguments = parser.parse_args()
    build(arguments.results, arguments.output)
