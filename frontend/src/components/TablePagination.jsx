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
  const firstVisiblePage = Math.max(1, Math.min(currentPage - 2, Math.max(1, totalPages - 4)));
  const visiblePages = totalPages > 0 ? Array.from(
    { length: Math.min(totalPages, 5) },
    (_, index) => firstVisiblePage + index,
  ).filter((p) => p <= totalPages) : [];

  return (
    <div className='table-pagination' aria-label='Phân trang'>
      <div className='table-pagination-left'>
        <label className='table-page-size'>
          <span>Số dòng:</span>
          <CustomSelect
            className='form-select table-page-size-select'
            aria-label='Số dòng mỗi trang'
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            disabled={disabled}
          >
            {[10, 25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </CustomSelect>
        </label>
        <span className='table-pagination-summary' aria-live='polite'>
          {totalItems
            ? `Hiển thị ${firstVisibleItem}–${lastVisibleItem} trên ${totalItems} ${itemLabel}`
            : `Không có ${itemLabel} nào`}
        </span>
      </div>

      <div className='table-pagination-controls'>
        <button
          type='button'
          className='btn btn-secondary btn-sm pagination-nav-btn'
          aria-label='Trang trước'
          onClick={() => onPageChange(currentPage - 1)}
          disabled={disabled || currentPage <= 1}
        >
          <ChevronLeft size={16} />
        </button>

        {totalPages > 0 ? (
          <>
            {totalPages > 5 && visiblePages[0] > 1 && (
              <>
                <button
                  type='button'
                  className='btn btn-secondary btn-sm table-page-number'
                  onClick={() => onPageChange(1)}
                  disabled={disabled}
                >
                  1
                </button>
                {visiblePages[0] > 2 && <span className='table-page-ellipsis'>…</span>}
              </>
            )}

            {visiblePages.map((pageNumber) => (
              <button
                key={pageNumber}
                type='button'
                className={'btn btn-sm table-page-number' + (pageNumber === currentPage ? ' is-current' : ' btn-secondary')}
                aria-current={pageNumber === currentPage ? 'page' : undefined}
                onClick={() => onPageChange(pageNumber)}
                disabled={disabled || pageNumber === currentPage}
              >
                {pageNumber}
              </button>
            ))}

            {totalPages > 5 && visiblePages[visiblePages.length - 1] < totalPages && (
              <>
                {visiblePages[visiblePages.length - 1] < totalPages - 1 && <span className='table-page-ellipsis'>…</span>}
                <button
                  type='button'
                  className='btn btn-secondary btn-sm table-page-number'
                  onClick={() => onPageChange(totalPages)}
                  disabled={disabled}
                >
                  {totalPages}
                </button>
              </>
            )}
          </>
        ) : (
          <button type='button' className='btn btn-sm table-page-number is-disabled-empty' disabled>
            1
          </button>
        )}

        <button
          type='button'
          className='btn btn-secondary btn-sm pagination-nav-btn'
          aria-label='Trang sau'
          onClick={() => onPageChange(currentPage + 1)}
          disabled={disabled || currentPage === 0 || currentPage >= totalPages}
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
