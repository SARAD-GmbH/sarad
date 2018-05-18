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

def print_dacm_value(dacm_value):
    print("ComponentName: " + dacm_value['component_name'])
    print("ValueName: " + dacm_value['value_name'])
    print(DacmInst.item_names[dacm_value['item_id']] + \
          ": " + dacm_value['result'])
    if dacm_value['datetime'] is not None:
        print("DateTime: " + dacm_value['datetime'].strftime("%c"))
    print("GPS: " + dacm_value['gps'])

def print_radon_scout_value(radon_scout_value):
    print(repr(("Radon: " + str(radon_scout_value['radon']) + " Bq/m³")))
    if radon_scout_value['datetime'] is not None:
        print("DateTime: " + radon_scout_value['datetime'].strftime("%c"))


