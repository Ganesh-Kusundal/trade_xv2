import { render, screen } from '@testing-library/react'
import { App } from '../App'

describe('App', () => {
  it('renders without crashing', () => {
    const { container } = render(<App />)
    expect(container).toBeInTheDocument()
  })

  it('renders version info', () => {
    render(<App />)
    const versionText = screen.queryByText(/v3\.0\.0/)
    expect(versionText).toBeInTheDocument()
  })
})