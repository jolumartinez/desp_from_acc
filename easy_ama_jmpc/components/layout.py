from dash import dcc, html

# Menú de navegación
def navbar():
    return html.Div(
        className="navbar",
        children=[
            dcc.Link('Home', href='/', className='nav-link'),
            dcc.Link('Análisis de Datos', href='/page1', className='nav-link'),
            dcc.Link('Estadísticas', href='/page2', className='nav-link'),
            dcc.Link('Configuraciones', href='/page3', className='nav-link'),
        ],
        style={
            'display': 'flex',
            'justify-content': 'space-around',
            'padding': '10px',
            'background-color': '#f8f9fa',
            'border-radius': '10px',
            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)'
        }
    )

# Layout de la página principal (Home)
def create_layout():
    return html.Div(
        className="container",
        children=[
            navbar(),
            html.H1("Dashboard de Análisis de Datos", style={'textAlign': 'center', 'margin-top': '20px'}),
            html.Div(
                className="upload-container",
                children=[
                    html.H2("Carga de archivos"),
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([
                            'Arrastra y suelta o ', html.A('Selecciona un archivo')
                        ]),
                        style={
                            'width': '100%',
                            'height': '60px',
                            'lineHeight': '60px',
                            'borderWidth': '1px',
                            'borderStyle': 'dashed',
                            'borderRadius': '10px',
                            'textAlign': 'center',
                            'margin': '10px',
                        },
                        multiple=False,  # Permitir solo un archivo a la vez
                    ),
                    html.Div(id='output-data-upload', style={'margin-top': '20px'}),
                ],
            ),
            # Primera fila: Cuadro de texto y gráfica principal
            html.Div(
                className="content-area",
                children=[
                    html.Div(
                        id="file-info-container",
                        children=[
                            html.H3("Información del archivo cargado"),
                            html.Pre(id='file-info', children="Aquí se mostrará la información del archivo"),
                        ],
                        style={
                            'width': '25%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'overflowY': 'auto',
                            'height': '400px',
                            'backgroundColor': '#f9f9f9',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="main-graph", style={'height': '400px'}),
                        ],
                        style={
                            'width': '70%',
                            'margin-left': '2%',
                            'padding': '20px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '40px',
                    'box-sizing': 'border-box'
                }
            ),
            # Segunda fila: Dos nuevas figuras
            html.Div(
                className="additional-graphs",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="additional-graph-1", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="additional-graph-2", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'margin-left': '2%',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '60px',
                    'box-sizing': 'border-box'
                }
            ),
            html.Div(
                className="two-graphs-half-width",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-16", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-17", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'margin-left': '2%',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '20px',
                    'box-sizing': 'border-box'
                }
            ),
            # Cuarta fila: Dos figuras en la mitad del ancho
            html.Div(
                className="two-graphs-half-width",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-4", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-5", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'margin-left': '2%',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '20px',
                    'box-sizing': 'border-box'
                }
            ),
            html.Div(
                className="two-graphs-half-width",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-6", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-7", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'margin-left': '2%',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '20px',
                    'box-sizing': 'border-box'
                }
            ),
            html.Div(
                className="two-graphs-half-width",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-8", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-9", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'margin-left': '2%',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '20px',
                    'box-sizing': 'border-box'
                }
            ),
            html.Div(
                className="two-graphs-half-width",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-18", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-19", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'margin-left': '2%',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '20px',
                    'box-sizing': 'border-box'
                }
            ),
            html.Div(
                className="two-graphs-half-width",
                children=[
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-12", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                    html.Div(
                        className="graph-container",
                        children=[
                            dcc.Graph(id="graph-13", style={'height': '400px'}),
                        ],
                        style={
                            'width': '48%',
                            'padding': '10px',
                            'border': '1px solid #ccc',
                            'border-radius': '10px',
                            'margin-left': '2%',
                            'box-shadow': '0px 4px 6px rgba(0, 0, 0, 0.1)',
                            'height': '400px',
                        }
                    ),
                ],
                style={
                    'display': 'flex',
                    'justify-content': 'space-between',
                    'width': '100%',
                    'margin-top': '20px',
                    'box-sizing': 'border-box'
                }
            ),
        ],
        style={'padding': '20px', 'max-width': '100%'}
    )
