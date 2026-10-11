extends Node
## 联机：建房、加入、玩家名单、岗位、开局切场景。自动加载为 Net。
## 主机说了算：潜艇的物理、驾驶椅、门、灯都由主机定，再广播给大家（舱内的同步见 scripts/net/sub_session.gd）。
## 没联网时 multiplayer 是 OfflineMultiplayerPeer，自己就是主机（id 1），同一套代码单人照样跑。
## 联机方式（局域网直连 / Steam / 归墟服务器）在 net_backend.gd，现在只有直连能用，另外两个是占位。
##
## 调试参数（`--` 之后）：
##   --host            开局就建房（局域网 / 直连）
##   --join=地址        开局就加入（IP 或 IP:端口）
##   --name=名字        玩家名（不存进设置）
##   --role=0~3        想要的岗位（驾驶、声呐、轮机、潜水员）
##   --autostart=N     主机：凑够 N 个人自动开局（开两个进程测联机用）
##   --net-log         联机的关键事件打到输出（`NET <帧号> <id> ...`，两个进程对着看）

signal roster_changed
## 大厅里显示的状态（连接中、被拒绝……）
signal status(text: String)
## 这一局的场景谁加载好了（之后才能给他发舱内的状态）
signal peer_loaded(id: int)
signal peer_left(id: int)

enum Role { PILOT, SONAR, ENGINEER, DIVER }
const ROLE_NAMES := ["驾驶", "声呐", "轮机", "潜水员"]
const ROLE_HINTS := [
	"操艇、深度、压载、上浮。只看得到仪表",
	"声呐、海图、找目标、听动静。唯一“看得见”外面的人",
	"电力、氧气、堵漏、修设备。艇的命在你手里",
	"机械臂、挂钩、出舱。外面的东西要靠你亲手拿回来",
]
const MAX_PLAYERS := 4
const LOBBY_SCENE := "res://scenes/lobby.tscn"
const GAME_SCENE := "res://scenes/deep_sea.tscn"
const JOIN_TIMEOUT := 10.0
const SETTINGS := "user://settings.cfg"

var backends := {
	"enet": NetBackend.ENetBackend.new(),
	"steam": NetBackend.SteamBackend.new(),
	"server": NetBackend.ServerBackend.new(),
}
## 玩家名单：peer id → {"name": 名字, "role": 岗位}。主机维护，每次变动整张广播
var players := {}
var local_name := ""
var in_game := false
## 回到大厅时要告诉玩家的话（主机断开、房间满了……）
var last_message := ""
var connecting := false

var _loaded := {}
var _join_serial := 0
var _want_role := -1


func _ready() -> void:
	var cfg := ConfigFile.new()
	cfg.load(SETTINGS)
	local_name = String(cfg.get_value("player", "name", ""))
	if local_name.is_empty():
		set_local_name("船员%03d" % (randi() % 1000))
	if DebugArgs.has("name"):
		local_name = DebugArgs.get_arg("name")
	if DebugArgs.has("role"):
		_want_role = clampi(int(DebugArgs.get_arg("role")), 0, 3)
	multiplayer.peer_disconnected.connect(_on_peer_disconnected)
	multiplayer.connected_to_server.connect(_on_connected)
	multiplayer.connection_failed.connect(func() -> void: leave("连不上主机"))
	multiplayer.server_disconnected.connect(func() -> void: leave("主机断开了"))
	roster_changed.connect(_check_autostart)
	roster_changed.connect(func() -> void: log_event("roster %s" % [players]))
	peer_loaded.connect(func(id: int) -> void: log_event("loaded %d" % id))
	peer_left.connect(func(id: int) -> void: log_event("left %d" % id))
	if DebugArgs.has("host"):
		host_game.call_deferred("enet")
	elif DebugArgs.has("join"):
		join_game.call_deferred("enet", DebugArgs.get_arg("join"))


## --net-log：打一行联机日志
func log_event(msg: String) -> void:
	if DebugArgs.has("net-log"):
		print("NET %d %d %s" % [Engine.get_process_frames(), multiplayer.get_unique_id(), msg])


func set_local_name(n: String) -> void:
	local_name = n.strip_edges().left(16)
	if local_name.is_empty():
		local_name = "船员"
	var cfg := ConfigFile.new()
	cfg.load(SETTINGS)
	cfg.set_value("player", "name", local_name)
	cfg.save(SETTINGS)


## 连着别人（建了房或加入了房间）；单人、没联网时是 false
func is_online() -> bool:
	return not (multiplayer.multiplayer_peer is OfflineMultiplayerPeer) \
		and multiplayer.multiplayer_peer.get_connection_status() == MultiplayerPeer.CONNECTION_CONNECTED


func is_host() -> bool:
	return multiplayer.is_server()


func my_id() -> int:
	return multiplayer.get_unique_id()


func player_name(id: int) -> String:
	return String(players.get(id, {}).get("name", "船员"))


func role_of(id: int) -> int:
	return int(players.get(id, {}).get("role", Role.PILOT))


## 这一局场景已经加载好的其他人（舱内状态只发给他们，没加载好的收到会找不到节点）
func loaded_peers() -> Array:
	var me := my_id()
	return _loaded.keys().filter(func(id: int) -> bool: return id != me)


# ---------------------------------------------------------------------------- 建房 / 加入 / 离开
func host_game(kind: String) -> bool:
	leave()
	var backend: NetBackend = backends[kind]
	var peer := backend.host(MAX_PLAYERS - 1)
	if peer == null:
		status.emit(backend.last_error)
		return false
	multiplayer.multiplayer_peer = peer
	players = {1: {"name": local_name, "role": _want_role if _want_role >= 0 else Role.PILOT}}
	status.emit("房间开好了")
	roster_changed.emit()
	return true


func join_game(kind: String, address: String) -> bool:
	leave()
	var backend: NetBackend = backends[kind]
	var peer := backend.join(address)
	if peer == null:
		status.emit(backend.last_error)
		return false
	multiplayer.multiplayer_peer = peer
	connecting = true
	status.emit("正在连接 %s ……" % address)
	_join_serial += 1
	var serial := _join_serial
	get_tree().create_timer(JOIN_TIMEOUT).timeout.connect(func() -> void:
		if connecting and serial == _join_serial:
			leave("连接超时：地址对不对？主机那边防火墙放行了吗？"))
	return true


## 单人下潜：不联网，自己当主机
func start_solo() -> void:
	leave()
	players = {1: {"name": local_name, "role": Role.PILOT}}
	_begin()


## 离开房间（或被断开）。在游戏里的话回大厅，reason 显示在大厅里
func leave(reason := "") -> void:
	var was := is_online() or connecting
	connecting = false
	if not (multiplayer.multiplayer_peer is OfflineMultiplayerPeer):
		multiplayer.multiplayer_peer.close()
		multiplayer.multiplayer_peer = OfflineMultiplayerPeer.new()
	players.clear()
	_loaded.clear()
	if not reason.is_empty():
		last_message = reason
		status.emit(reason)
	if was:
		roster_changed.emit()
	if in_game:
		in_game = false
		Story.goto_scene(LOBBY_SCENE)


func set_role(role: int) -> void:
	if is_host():
		_apply_role(1, role)
	else:
		_request_role.rpc_id(1, role)


## 主机：开局，所有人一起进潜艇
func start_game() -> void:
	if is_host() and not in_game:
		_begin.rpc()


## 进了这一局的场景（sub_session.gd 的 _ready 调）：告诉主机我好了
func mark_loaded() -> void:
	if is_host():
		_on_loaded(1)
	else:
		_peer_loaded.rpc_id(1)


func _check_autostart() -> void:
	if DebugArgs.has("autostart") and is_host() and not in_game \
			and players.size() >= int(DebugArgs.get_arg("autostart")):
		start_game()


func _on_connected() -> void:
	connecting = false
	status.emit("连上了，等主机开局")
	_register.rpc_id(1, local_name, _want_role)


func _on_peer_disconnected(id: int) -> void:
	_loaded.erase(id)
	peer_left.emit(id)
	if is_host() and players.has(id):
		players.erase(id)
		_broadcast_roster()


func _broadcast_roster() -> void:
	_roster.rpc(players)
	roster_changed.emit()


## 岗位不锁死（见 docs/design.md），但一个岗位只挂一个人：要的岗位有人了就和他换
func _apply_role(id: int, role: int) -> void:
	if not players.has(id) or role < 0 or role >= ROLE_NAMES.size():
		return
	var old: int = players[id].role
	for other: int in players:
		if other != id and players[other].role == role:
			players[other].role = old
	players[id].role = role
	_broadcast_roster()


func _free_role(want: int) -> int:
	var taken := players.values().map(func(p: Dictionary) -> int: return p.role)
	if want >= 0 and not want in taken:
		return want
	for r in ROLE_NAMES.size():
		if not r in taken:
			return r
	return Role.DIVER


func _on_loaded(id: int) -> void:
	_loaded[id] = true
	_loaded_set.rpc(_loaded.keys())
	peer_loaded.emit(id)


# ---------------------------------------------------------------------------- RPC
@rpc("any_peer", "reliable")
func _register(p_name: String, want_role: int) -> void:
	if not is_host():
		return
	var id := multiplayer.get_remote_sender_id()
	var reason := ""
	if in_game:
		reason = "他们已经下潜了，等这一趟回来再加入"
	elif players.size() >= MAX_PLAYERS:
		reason = "房间满了（最多 %d 人）" % MAX_PLAYERS
	if not reason.is_empty():
		_rejected.rpc_id(id, reason)
		# 等拒绝的消息发出去再断开
		get_tree().create_timer(0.5).timeout.connect(func() -> void:
			if multiplayer.multiplayer_peer is ENetMultiplayerPeer:
				multiplayer.multiplayer_peer.disconnect_peer(id))
		return
	players[id] = {"name": p_name.strip_edges().left(16), "role": _free_role(want_role)}
	_broadcast_roster()


@rpc("authority", "reliable")
func _roster(p: Dictionary) -> void:
	players = p
	roster_changed.emit()


@rpc("authority", "reliable")
func _rejected(reason: String) -> void:
	leave(reason)


@rpc("any_peer", "reliable")
func _request_role(role: int) -> void:
	if is_host():
		_apply_role(multiplayer.get_remote_sender_id(), role)


@rpc("authority", "call_local", "reliable")
func _begin() -> void:
	in_game = true
	_loaded.clear()
	last_message = ""
	Story.goto_scene(GAME_SCENE, "镇 海 号", "白沙门外海 · 一百四十海里")


@rpc("any_peer", "reliable")
func _peer_loaded() -> void:
	if is_host():
		_on_loaded(multiplayer.get_remote_sender_id())


@rpc("authority", "reliable")
func _loaded_set(ids: Array) -> void:
	var before := _loaded.duplicate()
	_loaded.clear()
	for id: int in ids:
		_loaded[id] = true
		if not before.has(id):
			peer_loaded.emit(id)
