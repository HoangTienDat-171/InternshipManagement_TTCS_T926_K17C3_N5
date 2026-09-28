import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import CustomSelect from './CustomSelect';

export default function TablePagination({
  page,
  pageSize,
  totalItems,
  totalPages,
  itemLabel = 'bản ghi',
  disabled = false,
  onPageChange,
  onPageSizeChange,
}) {
  const currentPage = totalPages ? Math.min(page, totalPages) : 0;
  const firstVisibleItem = totalItems ? ((currentPage - 1) * pageSize) + 1 : 0;
  const lastVisibleItem = Math.min(currentPage * pageSize, totalItems);
  const firstVisiblePage = Math.max(1, Math.min(currentPage - 2, totalPages - 4));
  const visiblePages = Array.from(
    { length: Math.min(totalPages, 5) },
    (_, index) => firstVisiblePage + index,
  );

  return (
    <div className='table-pagination' aria-label='Phân trang'>
      <span className='table-pagination-summary' aria-live='polite'>
        {totalItems
          ? 'Hiển thị ' + firstVisibleItem + '–' + lastVisibleItem + ' trên ' + totalItems + ' ' + itemLabel
          : 'Không có ' + itemLabel + ' nào'}
      </span>
      <div className='table-pagination-controls'>
        <label className='table-page-size'>
          <span>Số dòng</span>
          <CustomSelect
            className='form-select'
            aria-label='Số dòng mỗi trang'
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            disabled={disabled}
          >
            {[10, 25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </CustomSelect>
        </label>
        <button type='button' className='btn btn-secondary btn-sm' aria-label='Trang trước' onClick={() => onPageChange(currentPage - 1)} disabled={disabled || currentPage <= 1}>
          <ChevronLeft size={15} />
        </button>
        {totalPages > 5 && visiblePages[0] > 1 && (
          <>
            <button type='button' className='btn btn-secondary btn-sm table-page-number' onClick={() => onPageChange(1)}>1</button>
            <span className='table-page-ellipsis'>…</span>
          </>
        )}
        {visiblePages.map((pageNumber) => (
          <button
            key={pageNumber}
            type='button'
            className={'btn btn-sm table-page-number' + (pageNumber === currentPage ? ' is-current' : '')}
            aria-current={pageNumber === currentPage ? 'page' : undefined}
            onClick={() => onPageChange(pageNumber)}
            disabled={disabled || pageNumber === currentPage}
          >
            {pageNumber}
          </button>
        ))}
        {totalPages > 5 && visiblePages[visiblePages.length - 1] < totalPages && (
          <>
            <span className='table-page-ellipsis'>…</span>
            <button type='button' className='btn btn-secondary btn-sm table-page-number' onClick={() => onPageChange(totalPages)}>{totalPages}</button>
          </>
        )}
        <span className='table-page-count'>Trang {currentPage} / {totalPages}</span>
        <button type='button' className='btn btn-secondary btn-sm' aria-label='Trang sau' onClick={() => onPageChange(currentPage + 1)} disabled={disabled || currentPage === 0 || currentPage >= totalPages}>
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
}
