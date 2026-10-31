export class ApiError extends Error {
  status: number;
  code?: string;
  type?: string;
  title?: string;
  instance?: string;

  constructor(
    message: string,
    status: number,
    metadata: { code?: string; type?: string; title?: string; instance?: string } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = metadata.code;
    this.type = metadata.type;
    this.title = metadata.title;
    this.instance = metadata.instance;
  }
}
