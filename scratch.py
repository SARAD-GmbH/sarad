# for element in get_recent_msg:
#     byte = (element).to_bytes(1,'big')
#     ser.write(byte)
#     print(byte)
#     ser.reset_output_buffer()
#     time.sleep(0.01)
# time.sleep(0.05)

    f_nil = dict(name = 'no family', id = 0)
    f_modem = dict(name = 'modem family', id = 3, baudrates = [9600, 115200])

    # unicon1 = int.from_bytes(payload[5:7], byteorder='little', signed=False)
    # unicon2 = int.from_bytes(payload[7:9], byteorder='little', signed=False)
    # unicon3 = int.from_bytes(payload[9:11], byteorder='little', signed=False)
    # unicon4 = int.from_bytes(payload[11:], byteorder='little', signed=False)
    # print(unicon1)
    # print(unicon2)
    # print(unicon3)
    # print(unicon4)

def get_recent_readings(serial_port):
    get_recent_msg = b'\x42\x80\x7f\x14\x14\x00\x45'
    reply_length_recent_msg = 39
    checked_payload = get_message_payload(serial_port, get_recent_msg, reply_length_recent_msg)
    if checked_payload['is_valid']:
        try:
            payload = checked_payload['payload']
            sample_interval = payload[1]
            device_time_min = payload[2]
            device_time_h = payload[3]
            device_time_d = payload[4]
            device_time_m = payload[5]
            device_time_y = payload[6]
            radon = bytes_to_float(payload[7:11])
            radon_error = payload[11]
            thoron = bytes_to_float(payload[12:16])
            thoron_error = payload[16]
            temperature = bytes_to_float(payload[17:21])
            humidity = bytes_to_float(payload[21:25])
            pressure = bytes_to_float(payload[25:29])
            tilt = int.from_bytes(payload[29:], byteorder='little', signed=False)
            device_time = datetime(device_time_y + 2000, device_time_m,
                                   device_time_d, device_time_h, device_time_min)
            print(sample_interval)
            print(device_time)
            print(radon)
            print(radon_error)
            print(thoron)
            print(thoron_error)
            print(temperature)
            print(humidity)
            print(pressure)
            print(tilt)
        except ParsingError:
            print("Error parsing the payload.")
    else:
        print("The instrument doesn't reply.")

def get_battery_voltage(serial_port):
    get_battery_msg = b'\x42\x80\x7f\x0d\x0d\x00\x45'
    reply_length_battery_msg = 39
    checked_payload = get_message_payload(serial_port, get_battery_msg, reply_length_battery_msg)
    if checked_payload['is_valid']:
        try:
            payload = checked_payload['payload']
            voltage = 0.00323 * int.from_bytes(payload[1:], byteorder='little', signed=False)
            print(voltage)
        except ParsingError:
            print("Error parsing the payload.")
    else:
        print("The instrument doesn't reply.")
