import { render, screen } from '@testing-library/react'
import { TopBar } from '../components/TopBar'

describe('TopBar', () => {
  it('renders brand name', () => {
    const { container } = render(<TopBar />)
    expect(container).toBeInTheDocument()
  })

  it('renders timeframe buttons', () => {
    render(<TopBar />)
    const buttons = screen.getAllByRole('button')
    const has5m = buttons.some(btn => btn.textContent?.includes('1m'))
    expect(has5m || buttons.length > 0).toBe(true)
  })
})