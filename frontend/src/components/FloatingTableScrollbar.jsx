import { useEffect, useRef, useState } from 'react';

export default function FloatingTableScrollbar({ scrollContainerRef, refreshKey, label }) {
  const scrollbarRef = useRef(null);
  const [hasOverflow, setHasOverflow] = useState(false);

  useEffect(() => {
    const tableScroll = scrollContainerRef.current;
    const scrollbar = scrollbarRef.current;
    const spacer = scrollbar?.firstElementChild;
    if (!tableScroll || !scrollbar || !spacer) return undefined;

    const syncScrollbarSize = () => {
      const table = tableScroll.querySelector('table');
      const contentWidth = Math.max(tableScroll.scrollWidth, table?.scrollWidth || 0);
      const bounds = tableScroll.getBoundingClientRect();
      scrollbar.style.left = `${bounds.left}px`;
      scrollbar.style.width = `${tableScroll.clientWidth + 2}px`;
      spacer.style.width = `${contentWidth}px`;
      setHasOverflow(tableScroll.clientWidth < contentWidth);
      scrollbar.scrollLeft = tableScroll.scrollLeft;
    };
    const syncFromTable = () => {
      if (scrollbar.scrollLeft !== tableScroll.scrollLeft) scrollbar.scrollLeft = tableScroll.scrollLeft;
    };
    const syncFromScrollbar = () => {
      if (tableScroll.scrollLeft !== scrollbar.scrollLeft) tableScroll.scrollLeft = scrollbar.scrollLeft;
    };

    syncScrollbarSize();
    tableScroll.addEventListener('scroll', syncFromTable, { passive: true });
    scrollbar.addEventListener('scroll', syncFromScrollbar, { passive: true });
    window.addEventListener('resize', syncScrollbarSize);

    const resizeObserver = new ResizeObserver(syncScrollbarSize);
    resizeObserver.observe(tableScroll);
    const table = tableScroll.querySelector('table');
    if (table) resizeObserver.observe(table);

    return () => {
      tableScroll.removeEventListener('scroll', syncFromTable);
      scrollbar.removeEventListener('scroll', syncFromScrollbar);
      window.removeEventListener('resize', syncScrollbarSize);
      resizeObserver.disconnect();
    };
  }, [scrollContainerRef, refreshKey]);

  return (
    <div
      className={`floating-table-scrollbar${hasOverflow ? ' is-visible' : ''}`}
      ref={scrollbarRef}
      aria-label={label}
      role="region"
      tabIndex={hasOverflow ? 0 : -1}
    >
      <div className="floating-table-scrollbar-spacer" />
    </div>
  );
}
