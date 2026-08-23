---
name: Orbital Command
colors:
  surface: '#111417'
  surface-dim: '#111417'
  surface-bright: '#37393d'
  surface-container-lowest: '#0b0e11'
  surface-container-low: '#191c1f'
  surface-container: '#1d2023'
  surface-container-high: '#272a2e'
  surface-container-highest: '#323538'
  on-surface: '#e1e2e7'
  on-surface-variant: '#c1c7d1'
  inverse-surface: '#e1e2e7'
  inverse-on-surface: '#2e3134'
  outline: '#8b919a'
  outline-variant: '#41474f'
  surface-tint: '#9ccaff'
  primary: '#9ccaff'
  on-primary: '#003256'
  primary-container: '#005288'
  on-primary-container: '#91c5ff'
  inverse-primary: '#206298'
  secondary: '#a6e6ff'
  on-secondary: '#003543'
  secondary-container: '#14d1ff'
  on-secondary-container: '#00566b'
  tertiary: '#ffba20'
  on-tertiary: '#412d00'
  tertiary-container: '#684900'
  on-tertiary-container: '#fab400'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d0e4ff'
  primary-fixed-dim: '#9ccaff'
  on-primary-fixed: '#001d35'
  on-primary-fixed-variant: '#00497b'
  secondary-fixed: '#b7eaff'
  secondary-fixed-dim: '#4cd6ff'
  on-secondary-fixed: '#001f28'
  on-secondary-fixed-variant: '#004e60'
  tertiary-fixed: '#ffdea8'
  tertiary-fixed-dim: '#ffba20'
  on-tertiary-fixed: '#271900'
  on-tertiary-fixed-variant: '#5e4200'
  background: '#111417'
  on-background: '#e1e2e7'
  surface-variant: '#323538'
typography:
  display-lg:
    fontFamily: JetBrains Mono
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-lg-mobile:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1'
    letterSpacing: 0.1em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: '1.4'
spacing:
  unit: 4px
  gutter: 12px
  margin-safe: 24px
  container-gap: 16px
  density-compact: 4px
  density-comfortable: 12px
---

## Brand & Style

This design system is built for high-stakes, mission-critical environments where data density and precision are paramount. Inspired by aerospace telemetry and orbital mechanics interfaces, the aesthetic is industrial, technical, and uncompromisingly professional.

The UI employs a **Technical Minimalism** style blended with **Cyber-Industrial** elements. It prioritizes information over decoration, using sharp lines, monospaced typography, and subtle glowing accents to signify active power states. The emotional response is one of calm authority, reliability, and extreme clarity under pressure.

## Colors

The palette is optimized for low-light environments (dark mode by default) to reduce eye strain during extended monitoring sessions.

- **Primary (SpaceX Blue):** Reserved for primary mission actions and core brand elements.
- **Secondary (Electric Cyan):** Used for data visualization highlights, active telemetry streams, and focus indicators.
- **Tertiary (Alert Amber):** Strictly for warnings, cautionary states, and non-critical system alerts.
- **Neutral Stack:** Deep Space Black (#0B0E11) acts as the foundation, while Charcoal Gray (#1C1F26) defines container layers and UI surface separation.
- **Typography:** Headlines utilize pure high-contrast white for maximum legibility; secondary labels use muted silver-gray to establish hierarchy and reduce visual noise in high-density views.

## Typography

The typography system strikes a balance between technical character and functional readability. 

**JetBrains Mono** is utilized for all headings, labels, and numerical data to evoke a programmed, engineering-first feel. The monospaced nature ensures that fluctuating numerical values (telemetry, timers) do not cause horizontal layout shifts.

**Inter** is the workhorse for body copy and long-form descriptions. Its high x-height and neutral character ensure that dense technical documentation remains legible even at smaller scales.

Use `label-caps` for all metadata headers and table columns to clearly distinguish structure from content.

## Layout & Spacing

This design system uses a **Fixed Grid** model within fluid containers. The primary rhythm is based on a **4px baseline grid**, allowing for high-density information architecture.

- **Grid:** 12-column system for desktop with tight 12px gutters to maximize horizontal real estate for data tables and charts.
- **Margins:** Standard 24px safe area on all viewport edges.
- **Data Density:** Use the 4px `density-compact` unit for internal padding in data tables and input groups. Use the 12px `density-comfortable` unit for section spacing and major component separation.
- **Adaptation:** On mobile, the 12-column grid collapses to a 4-column layout. All monospaced labels remain at their fixed sizes, but headline-lg scales down to ensure single-line technical status readouts.

## Elevation & Depth

Depth is conveyed through **Tonal Layering** and **Subtle Glows** rather than traditional shadows.

- **Base Layer:** Deep Space Black (#0B0E11).
- **Surface Layer:** Charcoal Gray (#1C1F26) with a 1px solid border (#2D3139) to define interactive zones.
- **Active State:** Elements in focus or active states utilize an outer glow (`drop-shadow`) using the Electric Cyan color at 20-30% opacity. 
- **Overlays:** Modals and dropdowns use a background blur (12px) with a semi-transparent Charcoal Gray fill to maintain context of the background telemetry.
- **Dividers:** Use 1px borders in #2D3139. Avoid shadows on buttons; use border-color shifts and interior glows to indicate "on" states.

## Shapes

The shape language is strictly **Sharp (0px roundedness)**. 

This reinforces the industrial, mechanical nature of the interface. Sharp corners communicate precision and maximize screen space by allowing elements to sit perfectly flush against one another in a grid. This applies to buttons, input fields, cards, and modal windows.

## Components

- **Buttons:** Sharp corners. Primary buttons use SpaceX Blue background with white text. Secondary buttons use a 1px Charcoal border. On hover, apply a 4px Cyan left-edge border accent.
- **Input Fields:** Monospaced JetBrains Mono text for all entries. Background is Deep Space Black with a 1px border. When focused, the border turns Electric Cyan with a subtle outer glow.
- **Data Tables:** High-density. Row height should be fixed at 32px. Use `label-caps` for headers. Alternating row colors are not used; instead, use thin 1px dividers.
- **Status Chips:** Small, rectangular blocks. Success uses a Cyan outline; Warning uses Alert Amber; Critical uses a solid Red block.
- **Technical Overlays:** Use "crosshair" corner marks on major container corners to emphasize the technical/targeting aesthetic.
- **Scrollbars:** Custom slim-line scrollbars in #2D3139 to minimize visual intrusion into data areas.
- **Telemetry Cards:** Cards should feature a small monospaced ID or timestamp in the top-right corner to maintain the "logged data" aesthetic.