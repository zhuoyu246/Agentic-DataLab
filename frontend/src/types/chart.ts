export interface PlotlyData {
  x?: any[]
  y?: any[]
  type?: string
  mode?: string
  name?: string
  [key: string]: any
}

export interface PlotlyLayout {
  title?: string | { text: string }
  xaxis?: { title?: string }
  yaxis?: { title?: string }
  showlegend?: boolean
  [key: string]: any
}

export interface PlotlyConfig {
  responsive?: boolean
  displayModeBar?: boolean
  displaylogo?: boolean
  [key: string]: any
}

export interface ChartArtifact {
  type: 'chart'
  spec: {
    data: PlotlyData[]
    layout: PlotlyLayout
    config?: PlotlyConfig
  }
}
