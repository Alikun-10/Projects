package main

import (
	"crypto/sha256"
	"database/sql"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"
)

const (
	OP_AUTH          byte = 0x01
	OP_GPS_UPDATE    byte = 0x02
	OP_STATUS_CHANGE byte = 0x03
	OP_CHAT_SEND     byte = 0x04
	OP_CHAT_HISTORY  byte = 0x05
	OP_BATCH         byte = 0x06
	OP_PING          byte = 0x10
	OP_PONG          byte = 0x11
	OP_DEBUG_ATTACH  byte = 0x30
	OP_SET_DEBUG     byte = 0x31

	// Response status codes
	STATUS_OK            byte = 0x00
	STATUS_ERROR         byte = 0x01
	STATUS_AUTH_REQUIRED byte = 0x02
)


const (
	idleTimeout  = 30 * time.Second
	frameTimeout = 5 * time.Second
	writeTimeout = 10 * time.Second
)

type ConnState struct {
	mu            sync.Mutex
	authenticated bool
	userID        int
	username      string
	role          string
	deliveryID    int
	debugMode     bool
}

var (
	db          *sql.DB
	globalDebug bool
)

func main() {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://overeats:overeats_secret@postgres:5432/overeats?sslmode=disable"
	}
	globalDebug = os.Getenv("DEBUG_MODE") == "true"

	var err error
	for i := 0; i < 30; i++ {
		db, err = sql.Open("postgres", dbURL)
		if err == nil {
			err = db.Ping()
			if err == nil {
				break
			}
		}
		log.Printf("Waiting for database... attempt %d/30", i+1)
		time.Sleep(time.Second)
	}
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	log.Printf("LiveTrack daemon starting on :9090 (debug_mode=%v)", globalDebug)

	listener, err := net.Listen("tcp", ":9090")
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}
	defer listener.Close()

	go cleanupLoop()

	for {
		conn, err := listener.Accept()
		if err != nil {
			log.Printf("Accept error: %v", err)
			continue
		}
		go handleConnection(conn)
	}
}

func cleanupLoop() {
	for {
		time.Sleep(60 * time.Second)
		_, err := db.Exec("SELECT cleanup_old_data()")
		if err != nil {
			log.Printf("Cleanup error: %v", err)
		}
	}
}

func handleConnection(conn net.Conn) {
	defer conn.Close()

	state := &ConnState{}
	log.Printf("New connection from %s", conn.RemoteAddr())

	for {
		// Allow a generous gap before the NEXT frame starts, but no single
		// frame may keep us blocked indefinitely (see readFrame).
		if err := conn.SetReadDeadline(time.Now().Add(idleTimeout)); err != nil {
			return
		}

		opcode, payload, err := readFrame(conn)
		if err != nil {
			if err != io.EOF {
				log.Printf("Read error from %s: %v", conn.RemoteAddr(), err)
			}
			return
		}

		response := processCommand(state, opcode, payload)

		if err := conn.SetWriteDeadline(time.Now().Add(writeTimeout)); err != nil {
			return
		}
		if err := writeFrame(conn, response.status, response.data); err != nil {
			log.Printf("Write error to %s: %v", conn.RemoteAddr(), err)
			return
		}
	}
}

func readFrame(conn net.Conn) (byte, []byte, error) {
	header := make([]byte, 3)
	if _, err := io.ReadFull(conn, header); err != nil {
		return 0, nil, err
	}

	opcode := header[0]
	length := binary.BigEndian.Uint16(header[1:3])

	if length == 0 {
		return opcode, nil, nil
	}

	if err := conn.SetReadDeadline(time.Now().Add(frameTimeout)); err != nil {
		return 0, nil, err
	}

	payload := make([]byte, length)
	if _, err := io.ReadFull(conn, payload); err != nil {
		return 0, nil, err
	}

	return opcode, payload, nil
}

func writeFrame(conn net.Conn, status byte, data []byte) error {
	frame := make([]byte, 3+len(data))
	frame[0] = status
	binary.BigEndian.PutUint16(frame[1:3], uint16(len(data)))
	copy(frame[3:], data)
	_, err := conn.Write(frame)
	return err
}

type Response struct {
	status byte
	data   []byte
}

func okResponse(msg string) Response {
	return Response{status: STATUS_OK, data: []byte(msg)}
}

func errorResponse(msg string) Response {
	return Response{status: STATUS_ERROR, data: []byte(msg)}
}

func authRequiredResponse() Response {
	return Response{status: STATUS_AUTH_REQUIRED, data: []byte("Authentication required")}
}

func processCommand(state *ConnState, opcode byte, payload []byte) Response {
	switch opcode {
	case OP_AUTH:
		return handleAuth(state, payload)
	case OP_GPS_UPDATE:
		return handleGPSUpdate(state, payload)
	case OP_STATUS_CHANGE:
		return handleStatusChange(state, payload)
	case OP_CHAT_SEND:
		return handleChatSend(state, payload)
	case OP_CHAT_HISTORY:
		return handleChatHistory(state, payload)
	case OP_BATCH:
		return handleBatch(state, payload)
	case OP_PING:
		return Response{status: STATUS_OK, data: []byte("PONG")}
	case OP_DEBUG_ATTACH:
		return handleDebugAttach(state, payload)
	case OP_SET_DEBUG:
		return handleSetDebug(state, payload)
	default:
		return errorResponse(fmt.Sprintf("Unknown opcode: 0x%02x", opcode))
	}
}

func handleAuth(state *ConnState, payload []byte) Response {
	parts := strings.SplitN(string(payload), ":", 2)
	if len(parts) != 2 {
		return errorResponse("Invalid auth format. Expected username:password")
	}

	username := parts[0]
	password := parts[1]

	hash := sha256.Sum256([]byte(password))
	pwHash := hex.EncodeToString(hash[:])

	var userID int
	var role string
	err := db.QueryRow(
		"SELECT id, role FROM users WHERE username = $1 AND password_hash = $2",
		username, pwHash,
	).Scan(&userID, &role)

	if err != nil {
		return errorResponse("Invalid credentials")
	}

	state.mu.Lock()
	state.authenticated = true
	state.userID = userID
	state.username = username
	state.role = role
	state.mu.Unlock()

	return okResponse(fmt.Sprintf("Authenticated as %s (role=%s, id=%d)", username, role, userID))
}

func handleGPSUpdate(state *ConnState, payload []byte) Response {
	if !state.authenticated {
		return authRequiredResponse()
	}
	if state.role != "driver" {
		return errorResponse("Only drivers can send GPS updates")
	}

	parts := strings.SplitN(string(payload), ":", 2)
	if len(parts) != 2 {
		return errorResponse("Format: delivery_id:lat,lon")
	}

	deliveryID, err := strconv.Atoi(parts[0])
	if err != nil {
		return errorResponse("Invalid delivery ID")
	}

	coords := strings.Split(parts[1], ",")
	if len(coords) != 2 {
		return errorResponse("Format: lat,lon")
	}

	lat, err1 := strconv.ParseFloat(coords[0], 64)
	lon, err2 := strconv.ParseFloat(coords[1], 64)
	if err1 != nil || err2 != nil {
		return errorResponse("Invalid coordinates")
	}

	var driverID int
	err = db.QueryRow(
		"SELECT driver_id FROM deliveries WHERE id = $1", deliveryID,
	).Scan(&driverID)
	if err != nil || driverID != state.userID {
		return errorResponse("Not assigned to this delivery")
	}

	_, err = db.Exec(
		"UPDATE deliveries SET latitude = $1, longitude = $2 WHERE id = $3",
		lat, lon, deliveryID,
	)
	if err != nil {
		return errorResponse("Failed to update GPS")
	}

	return okResponse("GPS updated")
}

func handleStatusChange(state *ConnState, payload []byte) Response {
	if !state.authenticated {
		return authRequiredResponse()
	}
	if state.role != "driver" {
		return errorResponse("Only drivers can change delivery status")
	}

	parts := strings.SplitN(string(payload), ":", 2)
	if len(parts) != 2 {
		return errorResponse("Format: delivery_id:status")
	}

	deliveryID, err := strconv.Atoi(parts[0])
	if err != nil {
		return errorResponse("Invalid delivery ID")
	}
	newStatus := parts[1]

	var driverID int
	err = db.QueryRow(
		"SELECT driver_id FROM deliveries WHERE id = $1", deliveryID,
	).Scan(&driverID)
	if err != nil || driverID != state.userID {
		return errorResponse("Not assigned to this delivery")
	}

	_, err = db.Exec(
		"UPDATE deliveries SET status = $1 WHERE id = $2",
		newStatus, deliveryID,
	)
	if err != nil {
		return errorResponse("Failed to update status")
	}

	return okResponse("Status updated")
}

func handleChatSend(state *ConnState, payload []byte) Response {
	if !state.authenticated {
		return authRequiredResponse()
	}

	parts := strings.SplitN(string(payload), ":", 2)
	if len(parts) != 2 {
		return errorResponse("Format: delivery_id:message")
	}

	deliveryID, err := strconv.Atoi(parts[0])
	if err != nil {
		return errorResponse("Invalid delivery ID")
	}
	message := parts[1]

	authorized := false

	if state.role == "driver" {
		var driverID int
		err = db.QueryRow(
			"SELECT driver_id FROM deliveries WHERE id = $1", deliveryID,
		).Scan(&driverID)
		if err == nil && driverID == state.userID {
			authorized = true
		}
	}

	if state.role == "customer" {
		var customerID int
		err = db.QueryRow(
			`SELECT o.customer_id FROM deliveries d
			 JOIN orders o ON d.order_id = o.id
			 WHERE d.id = $1`, deliveryID,
		).Scan(&customerID)
		if err == nil && customerID == state.userID {
			authorized = true
		}
	}

	state.mu.Lock()
	if state.debugMode && state.deliveryID == deliveryID {
		authorized = true
	}
	state.mu.Unlock()

	if !authorized {
		return errorResponse("Not a participant in this delivery")
	}

	_, err = db.Exec(
		"INSERT INTO chat_messages (delivery_id, sender_id, message) VALUES ($1, $2, $3)",
		deliveryID, state.userID, message,
	)
	if err != nil {
		return errorResponse("Failed to send message")
	}

	return okResponse("Message sent")
}

func handleChatHistory(state *ConnState, payload []byte) Response {
	if !state.authenticated {
		return authRequiredResponse()
	}

	deliveryID, err := strconv.Atoi(string(payload))
	if err != nil {
		return errorResponse("Invalid delivery ID")
	}

	authorized := false

	if state.role == "driver" {
		var driverID int
		err = db.QueryRow(
			"SELECT driver_id FROM deliveries WHERE id = $1", deliveryID,
		).Scan(&driverID)
		if err == nil && driverID == state.userID {
			authorized = true
		}
	}

	if state.role == "customer" {
		var customerID int
		err = db.QueryRow(
			`SELECT o.customer_id FROM deliveries d
			 JOIN orders o ON d.order_id = o.id
			 WHERE d.id = $1`, deliveryID,
		).Scan(&customerID)
		if err == nil && customerID == state.userID {
			authorized = true
		}
	}

	state.mu.Lock()
	if state.debugMode && state.deliveryID == deliveryID {
		authorized = true
	}
	state.mu.Unlock()

	if !authorized {
		return errorResponse("Not a participant in this delivery")
	}

	rows, err := db.Query(
		`SELECT sender_id, message, created_at FROM chat_messages
		 WHERE delivery_id = $1 ORDER BY created_at ASC`, deliveryID,
	)
	if err != nil {
		return errorResponse("Failed to fetch messages")
	}
	defer rows.Close()

	var messages []string
	for rows.Next() {
		var senderID int
		var msg string
		var createdAt time.Time
		if err := rows.Scan(&senderID, &msg, &createdAt); err != nil {
			continue
		}
		messages = append(messages, fmt.Sprintf("[%d@%s] %s",
			senderID, createdAt.Format("15:04:05"), msg))
	}

	if len(messages) == 0 {
		return okResponse("No messages")
	}
	return okResponse(strings.Join(messages, "\n"))
}

func handleBatch(state *ConnState, payload []byte) Response {
	var results []string
	offset := 0

	for offset < len(payload) {
		if offset+3 > len(payload) {
			break
		}

		subOpcode := payload[offset]
		subLength := binary.BigEndian.Uint16(payload[offset+1 : offset+3])
		offset += 3

		if offset+int(subLength) > len(payload) {
			results = append(results, "ERROR: truncated sub-frame")
			break
		}

		subPayload := payload[offset : offset+int(subLength)]
		offset += int(subLength)

		resp := processCommand(state, subOpcode, subPayload)

		statusStr := "OK"
		if resp.status == STATUS_ERROR {
			statusStr = "ERR"
		}
		results = append(results, fmt.Sprintf("[%s] %s", statusStr, string(resp.data)))
	}

	return okResponse(strings.Join(results, "\n"))
}

func handleDebugAttach(state *ConnState, payload []byte) Response {
	if !state.authenticated {
		return authRequiredResponse()
	}

	state.mu.Lock()
	isDebug := state.debugMode
	state.mu.Unlock()

	if !isDebug {
		return errorResponse("Debug mode not enabled")
	}

	deliveryID, err := strconv.Atoi(string(payload))
	if err != nil {
		return errorResponse("Invalid delivery ID")
	}

	var exists int
	err = db.QueryRow("SELECT id FROM deliveries WHERE id = $1", deliveryID).Scan(&exists)
	if err != nil {
		return errorResponse("Delivery not found")
	}

	state.mu.Lock()
	state.deliveryID = deliveryID
	state.mu.Unlock()

	return okResponse(fmt.Sprintf("Attached to delivery %d", deliveryID))
}

func handleSetDebug(state *ConnState, payload []byte) Response {
	if !state.authenticated {
		return authRequiredResponse()
	}

	state.mu.Lock()
	state.debugMode = true
	state.mu.Unlock()

	if !globalDebug {
		return errorResponse("Debug mode is disabled in production")
	}

	return okResponse("Debug mode enabled")
}
