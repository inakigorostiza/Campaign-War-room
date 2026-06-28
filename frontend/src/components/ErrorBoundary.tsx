import { Component, type ReactNode } from "react";

interface Props {
  fallback: ReactNode;
  children: ReactNode;
}
interface State {
  failed: boolean;
}

/** Isolates a subtree (e.g. the WebGL globe) so its failure can't blank the app. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("Subtree error (isolated by ErrorBoundary):", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
