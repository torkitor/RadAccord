"""Shared publication styling; no measurement or acceptance logic."""
from pathlib import Path
import matplotlib as mpl
from matplotlib import font_manager
from PIL import Image

INK, BLUE, RED = '#222222', '#5F6F9F', '#EE7F6D'
RED_TEXT = '#AD594B'
GREY, LINE, PALE = '#595959', '#D9D9D9', '#F5F6F9'
GOLD = GREY  # The tolerance and unavailable-input accents are neutral.


def configure():
    # Require the intended locally installed face instead of silently substituting.
    for weight in ('normal', 'bold'):
        font_manager.findfont(font_manager.FontProperties(family='Arial', weight=weight),
                              fallback_to_default=False)
    mpl.rcParams.update({
        'font.family': 'Arial', 'font.size': 9, 'text.color': INK,
        'axes.labelcolor': INK, 'axes.labelsize': 9, 'axes.titlesize': 10,
        'axes.edgecolor': GREY, 'axes.linewidth': .65,
        'axes.spines.top': False, 'axes.spines.right': False,
        'xtick.color': INK, 'ytick.color': INK,
        'xtick.labelsize': 8.5, 'ytick.labelsize': 8.5,
        'xtick.major.width': .65, 'ytick.major.width': .65,
        'mathtext.fontset': 'custom', 'mathtext.rm': 'Arial',
        'mathtext.it': 'Arial:italic', 'mathtext.bf': 'Arial:bold',
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
        'svg.hashsalt': 'RadAccord-1.0.0',
        'savefig.facecolor': 'white', 'figure.facecolor': 'white',
    })


def export_figure(fig, output, name):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / f'{name}.png', dpi=600, metadata={'Software': None})
    fig.savefig(output / f'{name}.pdf', metadata={
        'Title': name, 'Creator': None, 'Producer': None,
        'CreationDate': None, 'ModDate': None})
    fig.savefig(output / f'{name}.svg', metadata={'Title': name, 'Date': None, 'Creator': None})
    with Image.open(output / f'{name}.png') as raster:
        raster.convert('RGB').save(output / f'{name}.tiff', dpi=(600, 600),
                                   compression='tiff_lzw')
