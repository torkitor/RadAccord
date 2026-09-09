"""Build the conceptual figure from development phantom 0; no result files read."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'software'))
sys.path.insert(0, str(ROOT / 'work'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from skimage.measure import marching_cubes
from physical_contracts import phantom
from figure_style import configure, export_figure, BLUE, RED, RED_TEXT, INK, GREY, LINE, PALE


configure()

fig = plt.figure(figsize=(6.5, 6.5), facecolor='white')
canvas = fig.add_axes([0, 0, 1, 1])
canvas.set(xlim=(0, 1), ylim=(0, 1))
canvas.axis('off')


def text(x, y, value, size=9.5, weight='normal', color=INK, ha='left', **kwargs):
    return canvas.text(x, y, value, fontsize=size, fontweight=weight,
                       color=color, ha=ha, va='center', **kwargs)


def box(x, y, w, h, edge=BLUE, face='white', linewidth=.7):
    patch = Rectangle((x, y), w, h, facecolor=face, edgecolor=edge, linewidth=linewidth)
    canvas.add_patch(patch)
    return patch


def arrow(start, end, color=GREY, width=.7, head=8):
    canvas.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=head,
                                    color=color, linewidth=width, shrinkA=0, shrinkB=0))


text(.04, .947, 'a', size=11, weight='bold')
text(.075, .947, 'Retain source and declare the operation', size=9)
text(.535, .947, 'b', size=11, weight='bold')
text(.570, .947, 'Separate the obligations', size=9)

# The left column contains a real generated ROI, not a stock silhouette.
box(.05, .507, .38, .380, face=PALE)
text(.24, .852, 'Trusted source + ROI', size=9, weight='bold', ha='center')
frame = phantom(0)
vertices, faces, _, _ = marching_cubes(frame.mask.astype(float), level=.5)
points = (frame.affine[:3, :3] @ vertices.T).T + frame.affine[:3, 3]
triangles = points[faces]
normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
light = np.array([-.4, -.5, .8]); light /= np.linalg.norm(light)
shade = .55 + .45 * np.maximum(normals @ light, 0)
base = np.array(matplotlib.colors.to_rgb('#97A1C0'))
colors = np.clip(base[None, :] * shade[:, None] + (1 - shade[:, None]) * .08, 0, 1)
mesh_ax = fig.add_axes([.061, .566, .355, .265], projection='3d', facecolor=PALE)
surface = Poly3DCollection(triangles, facecolors=colors, edgecolors='none', linewidths=0,
                           zsort='average', antialiased=True)
mesh_ax.add_collection3d(surface)
mid = (points.min(axis=0) + points.max(axis=0)) / 2
span = np.ptp(points, axis=0)
for axis, centre, extent in zip(('x', 'y', 'z'), mid, span):
    getattr(mesh_ax, f'set_{axis}lim')(centre - .55 * extent, centre + .55 * extent)
mesh_ax.set_box_aspect(span, zoom=1.7)
mesh_ax.view_init(elev=23, azim=-62)
mesh_ax.set_proj_type('ortho')
mesh_ax.set_axis_off()
text(.24, .536, 'Generated phantom · seed 0', size=8.5, color=GREY, ha='center')

box(.05, .325, .38, .138, edge=BLUE)
text(.24, .435, 'Declared transformation', size=9, weight='bold', color=BLUE, ha='center')
text(.07, .394, 'i = Bj       A′ = LAB', size=10)
text(.07, .353, 'I′(j) = declared sampling of I', size=10)
box(.05, .204, .38, .071, face=PALE)
text(.24, .24, 'Candidate image + ROI', size=9, ha='center')
arrow((.24, .507), (.24, .463), head=7)
arrow((.24, .325), (.24, .275), head=7)

# One input bus feeds three equally sized checks. It is not an outcome graph.
canvas.plot([.468, .468], [.239, .7955], color=GREY, linewidth=.7)
for y in (.655, .392, .239):
    canvas.plot([.430, .468], [y, y], color=GREY, linewidth=.7)

cards = [
    (.704, '1', 'Declared sampling',
     ['Positions · intensities · ROI',
      'Crop · pad · orient · resample',
      'Independent source evaluation']),
    (.477, '2', 'ROI coverage',
     ['Source voxel centres in the field',
      'Retained ROI or support loss',
      'An empty output is not accepted']),
    (.250, '3', 'Measurement reuse',
     ['New sampling: extract again',
      'Preserved input: apply valid laws',
      'Keep unverified features explicit']),
]
for y, number, heading, lines in cards:
    box(.535, y, .415, .183, face=PALE)
    text(.7425, y + .151, heading, size=9, weight='bold', color=BLUE, ha='center')
    for index, line in enumerate(lines):
        text(.7425, y + .108 - index * .039, line, size=8.5, ha='center')
    arrow((.468, y + .0915), (.535, y + .0915), head=7)

# These are per-obligation states, with no measured outcome counts.
canvas.plot([.950, .979, .979], [.7955, .7955, .174], color=GREY, linewidth=.7)
for y in (.5685, .3415):
    canvas.plot([.950, .979], [y, y], color=GREY, linewidth=.7)
arrow((.979, .174), (.742, .174), color=GREY, head=7, width=.7)
text(.04, .174, 'c', size=11, weight='bold')
text(.075, .174, 'Per-obligation decisions at each saved checkpoint', size=9)

states = [(.05, 'Satisfied', 'within the contract', BLUE, PALE),
          (.28, 'Violated', 'incompatible evidence', RED, '#FDF7F6'),
          (.51, 'Indeterminate', 'boundary ambiguity', GREY, 'white'),
          (.74, 'Unavailable', 'outside the domain', GREY, 'white')]
for x, state, note, color, fill in states:
    box(x, .043, .21, .091, edge=color, face=fill, linewidth=.65)
    text(x + .105, .101, state, size=8.8, weight='bold', color=RED_TEXT if state == 'Violated' else color, ha='center')
    text(x + .105, .068, note, size=7.1, color=INK, ha='center')

output = ROOT / 'docs' / 'figures' / 'sampling'
export_figure(fig, output, 'P2_Fig1')
plt.close(fig)
print('Created Figure 1 in Arial: 600 dpi PNG/TIFF and vector PDF/SVG.')
