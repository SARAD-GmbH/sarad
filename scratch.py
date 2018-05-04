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


