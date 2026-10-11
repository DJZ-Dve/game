class_name NetBackend
extends RefCounted
## 联机后端：负责建出一个 MultiplayerPeer（建房 / 加入），上层（net.gd）只管玩家名单和游戏状态，不关心底下走的是什么。
## 现在只有局域网 / 直连 IP（ENet）能用；Steam、归墟服务器先占位，接入时各写一个子类替换掉。

## 给大厅显示的名字
var title := ""
## 失败的原因（host / join 返回 null 时看这个）
var last_error := ""


## 能不能用（占位的后端返回 false，大厅里按钮灰掉）
func available() -> bool:
	return true


## 不能用时给玩家看的说明
func unavailable_reason() -> String:
	return ""


## 建房。成功返回已经开始监听的 peer，失败返回 null（原因在 last_error）
func host(_max_clients: int) -> MultiplayerPeer:
	last_error = "这个联机方式还没接入"
	return null


## 加入。address 的格式由各后端自己定（ENet 是 IP:端口，Steam 是大厅号……）
func join(_address: String) -> MultiplayerPeer:
	last_error = "这个联机方式还没接入"
	return null


## 局域网 / 直连 IP（ENet，UDP）。外网联机要主机那边做端口映射，所以正式上线还得靠 Steam 或中继服务器
class ENetBackend extends NetBackend:
	const DEFAULT_PORT := 24680

	func _init() -> void:
		title = "局域网 / 直连 IP"

	func host(max_clients: int) -> MultiplayerPeer:
		var peer := ENetMultiplayerPeer.new()
		var err := peer.create_server(DEFAULT_PORT, max_clients)
		if err != OK:
			last_error = "端口 %d 开不了（%s），是不是已经开着一个游戏？" % [DEFAULT_PORT, error_string(err)]
			return null
		return peer

	func join(address: String) -> MultiplayerPeer:
		var host_ip := address.strip_edges()
		var port := DEFAULT_PORT
		# 「IP:端口」；IPv6 地址本身带冒号，用 [::1]:端口 的写法
		if host_ip.begins_with("["):
			var close := host_ip.find("]")
			if close > 0:
				if host_ip.substr(close + 1).begins_with(":"):
					port = int(host_ip.substr(close + 2))
				host_ip = host_ip.substr(1, close - 1)
		elif host_ip.count(":") == 1:
			port = int(host_ip.get_slice(":", 1))
			host_ip = host_ip.get_slice(":", 0)
		if host_ip.is_empty():
			last_error = "没填主机地址"
			return null
		var peer := ENetMultiplayerPeer.new()
		var err := peer.create_client(host_ip, port)
		if err != OK:
			last_error = "连不上 %s:%d（%s）" % [host_ip, port, error_string(err)]
			return null
		return peer

	## 本机的局域网地址，建房后显示给主机，让他念给别人填
	static func lan_addresses() -> PackedStringArray:
		var out := PackedStringArray()
		for a in IP.get_local_addresses():
			if a.contains(":") or a.begins_with("127.") or a.begins_with("169.254."):
				continue
			if a.begins_with("10.") or a.begins_with("192.168.") or _is_172_private(a):
				out.append(a)
		return out

	static func _is_172_private(a: String) -> bool:
		if not a.begins_with("172."):
			return false
		var second := int(a.get_slice(".", 1))
		return second >= 16 and second <= 31


## 占位：Steam 联机（大厅、好友邀请、P2P 中继，不用端口映射）。
## 接入时装 GodotSteam（GDExtension），用 SteamMultiplayerPeer 建房 / 加入，address 是 Steam 大厅号
class SteamBackend extends NetBackend:
	func _init() -> void:
		title = "Steam 好友"

	func available() -> bool:
		return false

	func unavailable_reason() -> String:
		return "Steam 联机还没接入（要先上架 Steam、装 GodotSteam）"


## 占位：归墟自己的服务器（房间列表 + 中继转发，主机还是玩家自己，服务器只牵线、转包）。
## 服务器地址、协议都还没定；接入时这里连服务器拿房间号，再用中继的 peer 建房 / 加入
class ServerBackend extends NetBackend:
	## 服务器还没架，不要真的去连
	const SERVER_ADDRESS := ""

	func _init() -> void:
		title = "归墟服务器"

	func available() -> bool:
		return false

	func unavailable_reason() -> String:
		return "服务器还没架设（占位）"
