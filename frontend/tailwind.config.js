/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Dark industrial theme
        surface: {
          DEFAULT: '#0d1117',
          card:    '#161b22',
          border:  '#30363d',
          hover:   '#21262d',
        },
        accent: {
          blue:   '#388bfd',
          green:  '#3fb950',
          orange: '#d29922',
          red:    '#f85149',
          purple: '#8b949e',
        },
        risk: {
          critical: '#f85149',
          high:     '#d29922',
          normal:   '#3fb950',
          low:      '#388bfd',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      borderRadius: {
        card: '0.75rem',
      },
    },
  },
  plugins: [],
}
