# video proxy
此服务仅代理`.mp4`结尾的视频流，带有持久化 LRU (Least Recently Used) 缓存
## API
```
http(s)://service.domain/path?token=your-token&url=
```
`url`参数需要编码转义:
```JavaScript
// js
encodeURIComponent(url)
```
```python
# python
import urllib.parse
urllib.parse.quote(url, safe='')
```
## 项目环境变量（.env）

在项目根目录下创建 .env 文件，`TOKEN` 项必须填写，其他项可以省略，示例:

```
TOKEN=abcdef
APP_PATH=proxy
HOST=0.0.0.0
PORT=9000
CACHE_SIZE_GB=10
CACHE_DIR=/tmp/mp4cache
```

- **`TOKEN`: 验证令牌，防止滥用**
- `APP_PATH`: 服务路径，默认为空
- `PORT`: 服务监听端口，默认为 8000
- `HOST`: 默认绑定内网 `127.0.0.1`
- `CACHE_SIZE_GB`: 缓存大小，单位为GB，默认为 `2`
- `CACHE_DIR`: 缓存地址，默认为 `/tmp/mp4cache`
