from dash import html, dcc
from components.layout import navbar  # Importamos el menú de navegación

def layout():
    return html.Div(
        className="container",
        children=[
            navbar(),  # Menú de navegación
            html.H1("Análisis de Datos"),
            html.Div(
                className="graph-container",
                children=[
                    dcc.Graph(id="analysis-graph"),
                    html.P("Aquí puedes visualizar los gráficos de análisis de datos."),
                ],
            ),
        ]
    )
