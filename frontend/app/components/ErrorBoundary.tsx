'use client'

import { Component, type ReactNode } from 'react'
import * as Sentry from '@sentry/nextjs'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

// Catches render errors thrown by {children} without unmounting the
// surrounding shell chrome (sidebar/nav), so a broken page doesn't also
// take the navigation with it. Route-level error.tsx files handle the
// top-level "whole page crashed" case; this is the inner safety net for
// AppShell/AdminShell specifically.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: Error) {
    Sentry.captureException(error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 px-4 py-24 text-center">
          <p className="text-base font-semibold text-foreground">Something went wrong.</p>
          <p className="text-sm text-muted-foreground">
            This part of the page failed to load. Try refreshing.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
          >
            Refresh
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
