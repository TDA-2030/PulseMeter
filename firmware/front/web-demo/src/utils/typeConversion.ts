export const convertToNumbers = (obj: any): any => {
  if (typeof obj !== 'object' || obj === null) {
    return !isNaN(obj as any) && obj !== '' ? Number(obj) : obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(item => convertToNumbers(item));
  }

  const result: any = {};
  for (const key in obj) {
    result[key] = convertToNumbers(obj[key]);
  }
  return result;
};

export const formatTimestamp = (timestamp: number): string => {
  const date = new Date(timestamp * 1000);
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};