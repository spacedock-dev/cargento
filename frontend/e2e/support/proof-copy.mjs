export const copyProofPath = (path) =>
  !path.split(/[\\/]/).some((part) => ['test-results', '__pycache__'].includes(part));
