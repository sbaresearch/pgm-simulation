from pandapower.plotting.plotly.traces import _get_branch_geodata_plotly, create_edge_center_trace
from plotly.graph_objs.scatter.marker import ColorBar
from plotly.graph_objs.scatter import Line, Marker
from collections.abc import Iterable
from pandapower.plotting.plotly.get_colors import get_plotly_color, get_plotly_cmap
import numpy as np
import plotly.graph_objects as go
import pandas as pd
from matplotlib import colormaps
from matplotlib.colors import to_rgb

bus_size = 10
line_width = 2

# =========== This is a replacement for the def get_plotly_color_palette function with better colormap


def get_plotly_color_palette(n, palette="brg") -> list[str]:
    colormap = colormaps[palette]
    colors = colormap(np.linspace(0, 1.0, n))

    color_strings = []
    for color in colors:
        plotly_col = [255 * _c for _c in to_rgb(color)]
        color_strings.append(f"rgb({plotly_col[0]:.0f}, {plotly_col[1]:.0f}, {plotly_col[2]:.0f})")

    return color_strings

# =========== This is a replacement for the draw_traces function that can create a custom layout


def draw_traces(traces, save_path, title, showlegend=False):
    # Create layout with title
    layout = go.Layout(
        title=dict(
            text=title,
            x=0.5,  # Center title
            xanchor='center'
        ),
        showlegend=showlegend,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            scaleanchor='y',
            scaleratio=294.45/567.4,  # Austrias height/lenght (km)
            constrain='domain'
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False
        )
    )

    # Manually create the figure
    fig = go.Figure(data=traces, layout=layout)

    # Save to HTML
    fig.write_html(save_path, auto_open=False)


# =========== This is a replacement for the broken create branch trace from pandapower


def _create_branch_trace(net, branches=None, use_branch_geodata=True, cbar_title="",
                         width=1.0, color='grey', infofunc=None, trace_name='lines',
                         legendgroup=None, cmap=None, show_colorbar=True,
                         cmap_vals=None, cmin=None, cmax=None, cpos=1.1, branch_element='line', node_element='bus',
                         cmap_vals_category='loading_percent', hoverlabel=None, dash="solid"):
    """
    Annoyingly, the branch trace funciton in pandapower is broken, so I made my own and fixed it.
       """

    color = get_plotly_color(color)

    # defining branches (lines) to be plot
    branches = net[branch_element].index.tolist() if branches is None else list(branches)
    branches_to_plot = net[branch_element].loc[list(set(net[branch_element].index) & (set(branches)))]

    no_go_branches_to_plot = None
    use_branch_geodata = use_branch_geodata if net[branch_element]["geo"].dropna().shape[0] > 0 else False
    if use_branch_geodata:
        branches_to_plot = branches_to_plot.loc[np.intersect1d(branches_to_plot.index,
                                                               net[branch_element].index)]
    else:
        branches_with_geodata = branches_to_plot['from_' + node_element].isin(
            net[node_element].dropna(subset=["geo"]).index) & \
            branches_to_plot['to_' + node_element].isin(
            net[node_element].dropna(subset=["geo"]).index)
        branches_to_plot = branches_to_plot.loc[branches_with_geodata]
    cmap_branches = None
    if cmap is not None:
        # workaround: if colormap plot is used, each line need to be separate scatter object because
        # plotly still doesn't support appropriately colormap for line objects
        # TODO correct this when plotly solves existing github issue about Line colorbar

        cmap = 'jet' if cmap is True else cmap

        if cmap_vals is not None:
            if not isinstance(cmap_vals, np.ndarray):
                cmap_vals = np.asarray(cmap_vals)
        else:
            cmap_vals = net['res_' + branch_element].loc[branches_to_plot.index,
                                                         cmap_vals_category].values

        cmap_branches = get_plotly_cmap(cmap_vals, cmap_name=cmap, cmin=cmin, cmax=cmax)
        if len(cmap_branches) == len(net[branch_element]):
            # some branches are not plotted although cmap_value were provided for all branches
            branch_idx_map = dict(zip(net[branch_element].loc[branches].index.tolist(), range(len(branches))))
            cmap_branches = [cmap_branches[branch_idx_map[idx]] for idx in branches_to_plot.index]
        else:
            assert len(cmap_branches) == len(branches_to_plot), \
                "Different amounts of cmap values and branches to plot were supplied"
    branch_traces = []
    for col_i, (idx, branch) in enumerate(branches_to_plot.iterrows()):
        line_color = color
        line_info = branch['name'] if infofunc is None else infofunc.at[idx]
        if cmap is not None:
            line_color = cmap_branches[col_i]  # type: ignore

        line_trace = dict(type='scatter',
                          text=[],
                          hoverinfo='text',
                          mode='lines',
                          name=trace_name,
                          line=Line(width=width, color=color, dash=dash),
                          showlegend=False,
                          legendgroup=legendgroup)

        line_trace['x'], line_trace['y'] = _get_branch_geodata_plotly(net,
                                                                      branches_to_plot.loc[idx:idx],
                                                                      use_branch_geodata,
                                                                      branch_element, node_element)

        line_trace['line']['color'] = line_color  # type: ignore

        line_trace['text'] = line_info

        branch_traces.append(line_trace)

    # enable legend for one element to make the legend group show up in the legend:
    branch_traces[0]["showlegend"] = True

    if show_colorbar and cmap is not None:

        cmin = cmap_vals.min() if cmin is None else cmin  # type: ignore
        cmax = cmap_vals.max() if cmax is None else cmax  # type: ignore

        # THIS IS WHERE I CHANGES STUFF
        cbar_cmap_name = 'Jet' if cmap == 'jet' else cmap
        # workaround to get colorbar for branches (an unvisible node is added)
        # get x and y of first line.from_bus:
        import ast
        x, y = ast.literal_eval(net.bus.loc[net.line.from_bus[0]].geo)["coordinates"]
        # x, y = geojson.utils.coords(net[node_element].loc(net[branch_element][f"from_{node_element}"][net[branch_element].index[0]], "geo"))
        branches_cbar = dict(type='scatter', x=[x], y=[y], mode='markers',
                             marker=Marker(size=0, cmin=cmin, cmax=cmax,
                                           color='rgb(255,255,255)',
                                           opacity=0,
                                           colorscale=cbar_cmap_name,
                                           colorbar=ColorBar(thickness=10,
                                                                x=cpos),
                                           ))

        branches_cbar['marker']['colorbar']['title'] = cbar_title  # type: ignore

        branches_cbar['marker']['colorbar']['title']['side'] = 'right'  # type: ignore

        branch_traces.append(branches_cbar)

    # sort infofunc so that it is the correct order lines_to_plot + no_go_lines_to_plot
    if infofunc is not None:
        if not isinstance(infofunc, pd.Series) and isinstance(infofunc, Iterable) and \
                len(infofunc) == len(net[branch_element]):  # type: ignore
            infofunc = pd.Series(index=net[branch_element].index, data=infofunc)  # type: ignore
        assert isinstance(infofunc, pd.Series), \
            "infofunc should be a pandas series with the net.{}.index to the infofunc contents" \
            .format(branch_element)
        sorted_idx = branches_to_plot.index.tolist()
        if no_go_branches_to_plot is not None:
            sorted_idx += no_go_branches_to_plot.index.tolist()
        infofunc = infofunc.loc[sorted_idx]
    center_trace = create_edge_center_trace(branch_traces, color=color, infofunc=infofunc,
                                            use_line_geo=use_branch_geodata,
                                            showlegend=False, legendgroup=legendgroup,
                                            hoverlabel=hoverlabel)
    branch_traces.append(center_trace)

    return branch_traces
