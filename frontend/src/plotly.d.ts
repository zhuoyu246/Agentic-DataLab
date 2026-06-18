declare module 'plotly.js-dist-min' {
  const Plotly: {
    react: (...args: any[]) => Promise<void>
    purge: (element: HTMLElement) => void
    Plots: {
      resize: (element: HTMLElement) => void
    }
  }

  export default Plotly
}
