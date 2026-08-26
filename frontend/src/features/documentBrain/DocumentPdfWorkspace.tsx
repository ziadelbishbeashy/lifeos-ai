type Props = {
  documentId: number;
  filename: string;
  pdfUrl: string;
};

export function DocumentPdfWorkspace({ documentId, filename, pdfUrl }: Props) {
  return (
    <div
      className="db-pdf-modal"
      data-db-pdf-modal
      data-db-document-id={String(documentId)}
      data-db-pdf-url={pdfUrl}
      data-db-document-name={filename}
      data-db-pdf-semantic-search-url={`/api/v1/documents/${documentId}/semantic-search`}
      data-db-pdf-ocr-layout-url={`/api/v1/documents/${documentId}/ocr/layout`}
      aria-hidden="true"
    >
      <div className="db-pdf-modal-backdrop" data-db-close-pdf />

      <section
        className="db-pdf-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="db-pdf-viewer-title"
        tabIndex={-1}
      >
        <header className="db-pdf-titlebar">
          <div className="db-pdf-title-copy">
            <span className="db-kicker">Document viewer</span>
            <h2 id="db-pdf-viewer-title">{filename}</h2>
          </div>

          <div className="db-pdf-title-actions">
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-new-tab title="Open the PDF in a new browser tab">
              New tab
            </button>
            <button type="button" className="db-pdf-close-button" data-db-close-pdf aria-label="Close PDF viewer" title="Close">
              ×
            </button>
          </div>
        </header>

        <div className="db-pdf-toolbar" data-db-pdf-toolbar>
          <div className="db-pdf-toolbar-group">
            <button
              type="button"
              className="db-pdf-toolbar-button db-pdf-sidebar-toggle"
              data-db-pdf-sidebar-toggle
              aria-pressed="true"
              title="Show or hide thumbnails and semantic search"
            >
              Sidebar
            </button>
          </div>

          <div className="db-pdf-toolbar-group db-pdf-page-controls">
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-previous title="Previous page">‹</button>
            <label className="db-pdf-page-input-wrap">
              <span className="sr-only">Page number</span>
              <input type="number" min="1" defaultValue="1" inputMode="numeric" data-db-pdf-page-input />
              <span>/</span>
              <strong data-db-pdf-page-count>—</strong>
            </label>
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-next title="Next page">›</button>
          </div>

          <div className="db-pdf-toolbar-group db-pdf-zoom-controls">
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-zoom-out title="Zoom out">−</button>
            <span className="db-pdf-zoom-label" data-db-pdf-zoom-label>Fit width</span>
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-zoom-in title="Zoom in">+</button>
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-fit-width title="Fit page to viewer width">Fit width</button>
          </div>

          <div className="db-pdf-toolbar-group db-pdf-document-controls">
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-rotate-left title="Rotate left">↺</button>
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-rotate-right title="Rotate right">↻</button>
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-print title="Print PDF">Print</button>
            <button type="button" className="db-pdf-toolbar-button" data-db-pdf-download title="Download PDF">Download</button>
          </div>
        </div>

        <div className="db-pdf-progress" data-db-pdf-progress hidden>
          <div className="db-pdf-progress-bar" data-db-pdf-progress-bar />
        </div>

        <div className="db-pdf-workspace" data-db-pdf-workspace>
          <aside className="db-pdf-sidebar" data-db-pdf-sidebar>
            <div className="db-pdf-sidebar-tabs" role="tablist">
              <button type="button" className="db-pdf-sidebar-tab is-active" data-db-pdf-sidebar-view="pages">Pages</button>
              <button type="button" className="db-pdf-sidebar-tab" data-db-pdf-sidebar-view="find">Smart search</button>
            </div>

            <div className="db-pdf-sidebar-panel is-active" data-db-pdf-sidebar-panel="pages">
              <div className="db-pdf-thumbnails" data-db-pdf-thumbnails aria-label="PDF page thumbnails" />
            </div>

            <div className="db-pdf-sidebar-panel" data-db-pdf-sidebar-panel="find">
              <form className="db-pdf-find-form" data-db-pdf-find-form>
                <label>
                  <span>Search by meaning</span>
                  <div className="db-pdf-find-row">
                    <input
                      type="search"
                      autoComplete="off"
                      maxLength={500}
                      placeholder="Search a topic or concept..."
                      data-db-pdf-find-input
                    />
                    <button type="submit" className="db-pdf-toolbar-button">Search</button>
                  </div>
                </label>
              </form>

              <p className="db-pdf-find-status" data-db-pdf-find-status>
                LifeOS will highlight related passages in the PDF.
              </p>

              <div className="db-pdf-match-navigation" data-db-pdf-match-navigation hidden>
                <button type="button" className="db-pdf-toolbar-button" data-db-pdf-match-previous title="Previous related passage">‹</button>
                <strong data-db-pdf-match-position>0 of 0</strong>
                <button type="button" className="db-pdf-toolbar-button" data-db-pdf-match-next title="Next related passage">›</button>
              </div>

              <div className="db-pdf-find-results" data-db-pdf-find-results />
            </div>
          </aside>

          <main className="db-pdf-stage" data-db-pdf-stage>
            <div className="db-pdf-loading" data-db-pdf-loading>
              <span className="db-pdf-spinner" aria-hidden="true" />
              <strong>Opening PDF…</strong>
              <small>Loading the protected document viewer.</small>
            </div>

            <div className="db-pdf-error" data-db-pdf-error hidden>
              <strong>LifeOS could not open the PDF viewer.</strong>
              <p data-db-pdf-error-message>Try opening the document in a new browser tab.</p>
              <button type="button" className="workspace-secondary-button" data-db-pdf-error-new-tab>Open in new tab</button>
            </div>

            <div className="db-pdf-canvas-wrap" data-db-pdf-canvas-wrap hidden>
              <div className="db-pdf-page-stack" data-db-pdf-page-stack>
                <canvas data-db-pdf-canvas />
                <div className="db-pdf-text-layer" data-db-pdf-text-layer aria-label="Selectable PDF text" />
              </div>
            </div>
          </main>
        </div>

        <div className="db-pdf-native-fallback" data-db-pdf-native-fallback hidden>
          <div className="db-pdf-fallback-note">
            <strong>Using your browser&apos;s PDF viewer.</strong>
            <span>The embedded PDF.js viewer could not start. Open the source in a new tab if the browser blocks inline display.</span>
          </div>
          <iframe title="PDF document" data-db-pdf-fallback-frame />
        </div>

        <div className="db-pdf-selection-toolbar" data-db-pdf-selection-toolbar hidden role="toolbar" aria-label="Selected PDF text actions">
          <button type="button" className="db-pdf-selection-primary" data-db-pdf-selection-ask>Ask about this</button>
          <button type="button" className="db-pdf-selection-secondary" data-db-pdf-selection-copy>Copy</button>
        </div>

        <footer className="db-pdf-statusbar">
          <span data-db-pdf-status>Ready</span>
          <span className="db-pdf-shortcuts">←/→ pages · Ctrl+F smart search · Esc close</span>
        </footer>
      </section>
    </div>
  );
}
