export const sanitizePhone = (value) => value.replace(/\D/g, '').slice(0, 10);
export const isValidVietnamPhone = (value) => /^(03|05|07|08|09)\d{8}$/.test(value);
