import random
import uuid
import copy


# example configuration for DMPR daemon
exa_conf = """
    "id" : "ace80ef4-d284-11e6-bf26-cec0c932ce01",
    "rtn-msg-interval" : "30",
    "rtn-msg-interval-jitter" : "7",
    "rtn-msg-hold-time" : "90",
    "mcast-v4-tx-addr" : "224.0.1.1",
    "mcast-v6-tx-addr" : "ff05:0:0:0:0:0:0:2",
    "proto-transport-enable"  : [ "v4" ],
    "interfaces" : [
      { "name" : "wlan0", "addr-v4" : "10.0.0.1", "link-characteristics" : { "bandwidth" : "100000", "loss" : "0" , "cost" : "1" } },
      { "name" : "tetra0", "addr-v4" : "10.0.0.1", "link-characteristics" : { "bandwidth" : "10000",  "loss" : "0" , "cost" : "0" } }
    ],
    "networks" : [
       { "proto": "v4", "prefix" : "192.168.1.0", "prefix-len" : "24" },
       { "proto": "v4", "prefix" : "192.168.2.0", "prefix-len" : "24" },
       { "proto": "v4", "prefix" : "10.10.0.0",   "prefix-len" : "16" },
       { "proto": "v6", "prefix" : "fdcb:523:1111::", "prefix-len" : "48" },
       { "proto": "v6", "prefix" : "fd6a:6ad:b07f:ffff::", "prefix-len" : "64" }
    }
"""

class ConfigurationException(Exception): pass
class InternalException(Exception): pass

class DMPRConfigDefaults(object):
    rtn_msg_interval = "30"
    rtn_msg_interval_jitter = str(int(int(rtn_msg_interval) / 4))
    rtn_msg_hold_time = str(int(rtn_msg_interval) * 3)

    # default bandwidth for a given interface in bytes/second
    # bytes/second enabled dmpr deployed in low bandwidth environments
    # normally this value should be fetched from a interface information
    # or by active measurements.
    # Implementers SHOULD quantise values into a few classes to reduce the
    # DMPR routing packet size.
    # E.g. 1000, 5000, 10000, 100000, 1000000, 100000000, 100000000
    LINK_CHARACTERISITCS_BANDWIDTH = "5000"
    # default loss is in percent for a given path
    # Implementers SHOULD quantise values into a few classes to reduce the
    # DMPR routing packet size.
    # e.g. 0, 5, 10, 20, 40, 80
    LINK_CHARACTERISITCS_LOSS = "0"
    # default link cost in a hypothetical currency, the higher the more valuable
    # e.g. wifi can be 0, LTE can be 100, satelite uplink can be 1000
    LINK_CHARACTERISITCS_COST = "0"


class DMPR(object):

    def __init__(self, log=None):
        assert(log)
        self._conf = None
        self._time = None
        self.log = log
        self.stop(init=True)


    def register_configuration(self, configuration):
        """ register and setup configuration. Raise
            an error when values are wrongly configured """
        assert(configuration)
        assert isinstance(configuration, dict)
        self.process_conf(configuration)


    def process_conf(self, configuration):
        """ convert external python dict configuration
            into internal configuration and check values """
        assert(configuration)
        self._conf = {}
        cmd = "rtn-msg-interval"
        self._conf[cmd] = configuration.get(cmd, DMPRConfigDefaults.rtn_msg_interval)
        cmd = "rtn-msg-interval-jitter"
        self._conf[cmd] = configuration.get(cmd, DMPRConfigDefaults.rtn_msg_interval_jitter)
        cmd = "rtn-msg-hold-time"
        self._conf[cmd] = configuration.get(cmd, DMPRConfigDefaults.rtn_msg_hold_time)
        if "id" not in configuration:
            msg = "configuration contains no id! A id must be unique, it can be \
                   randomly generated but for better performance and debugging \
                   capabilities this generated ID should be saved permanently \
                   (e.g. at a local file) to survive daemon restarts"
            raise ConfigurationException(msg)
        if not isinstance(configuration["id"], str):
            msg = "id must be a string!"
            raise ConfigurationException(msg)
        self._conf["id"] = configuration["id"]
        if not "interfaces" in configuration:
            msg = "No interface configurated, need at least one"
            raise ConfigurationException(msg)
        self._conf["interfaces"] = configuration["interfaces"]
        if not isinstance(self._conf["interfaces"], list):
            msg = "interfaces must be a list!"
            raise ConfigurationException(msg)
        if len(self._conf["interfaces"]) <= 0:
            msg = "at least one interface must be configured!"
            raise ConfigurationException(msg)
        for interface_data in self._conf["interfaces"]:
            if not isinstance(interface_data, dict):
                msg = "interface entry must be dict: {}".format(interface_data)
                raise ConfigurationException(msg)
            if "name" not in interface_data:
                msg = "interfaces entry must contain at least a \"name\""
                raise ConfigurationException(msg)
            if "addr-v4" not in interface_data:
                msg = "interfaces entry must contain at least a \"addr-v4\""
                raise ConfigurationException(msg)
            if "link-characteristics" not in interface_data:
                msg = "interfaces has no link characterstics, default some \"link-characteristics\""
                now = self._get_time(priv_data=self._get_time_priv_data)
                self.log.warning(msg, time=now)
                interface_data["link-characteristics"] = dict()
                interface_data["link-characteristics"]["bandwidth"] = DMPRConfigDefaults.LINK_CHARACTERISITCS_BANDWIDTH
                interface_data["link-characteristics"]["loss"] = DMPRConfigDefaults.LINK_CHARACTERISITCS_LOSS
                interface_data["link-characteristics"]["cost"] = DMPRConfigDefaults.LINK_CHARACTERISITCS_COST
        if "networks" in configuration:
            if not isinstance(configuration["networks"], list):
                msg = "networks must be a list!"
                raise ConfigurationException(msg)
            for network in configuration["networks"]:
                if not isinstance(network, dict):
                    msg = "interface entry must be dict: {}".format(network)
                    raise ConfigurationException(msg)
                if not "proto" in network:
                    msg = "network must contain proto key: {}".format(network)
                    raise ConfigurationException(msg)
                if not "prefix" in network:
                    msg = "network must contain prefix key: {}".format(network)
                    raise ConfigurationException(msg)
                if not "prefix-len" in network:
                    msg = "network must contain prefix-len key: {}".format(network)
                    raise ConfigurationException(msg)
            # seens fine, save it as it is
            self._conf["networks"] = configuration["networks"]
        if "mcast-v4-tx-addr" not in configuration:
            msg = "no mcast-v4-tx-addr configured!"
            raise ConfigurationException(msg)
        self._conf["mcast-v4-tx-addr"] = configuration["mcast-v4-tx-addr"]
        if "mcast-v6-tx-addr" not in configuration:
            msg = "no mcast-v6-tx-addr configured!"
            raise ConfigurationException(msg)
        self._conf["mcast-v6-tx-addr"] = configuration["mcast-v6-tx-addr"]


    def _check_outdated_route_entries(self):
        route_recalc_required = False
        # iterate over all interfaces
        for interface, v in self._rtd["interfaces"].items():
            dellist = []
            # iterate over all neighbors
            for router_id, vv in v["rx-msg-db"].items():
                now = self._get_time(priv_data=self._get_time_priv_data)
                if now - vv["rx-time"] > int(self._conf["rtn-msg-hold-time"]):
                    msg = "outdated entry from {} received at {}, interface: {} - drop it"
                    self.log.debug(msg.format(router_id, vv["rx-time"], interface),
                                   time=now)
                    dellist.append(router_id)
            for id_ in dellist:
                route_recalc_required = True
                del v["rx-msg-db"][id_]
        return route_recalc_required


    def conf_originator_addr_by_iface_v6(self, iface_name):
        for iface_data in self._conf["interfaces"]:
            if iface_data['name'] == iface_name:
                return iface_data['addr-v6']
        return None


    def conf_originator_addr_by_iface_v4(self, iface_name):
        for iface_data in self._conf["interfaces"]:
            if iface_data['name'] == iface_name:
                return iface_data['addr-v4']
        return None


    def conf_originator_addr_by_iface(self, proto, iface_name):
        if proto == "v4":
            return self.conf_originator_addr_by_iface_v4(iface_name)
        if proto == "v6":
            return self.conf_originator_addr_by_iface_v6(iface_name)
        raise InternalException("v4 or v6 not something else")


    def create_routing_msg(self, interface_name):
        packet = dict()
        packet['id'] = self._conf["id"]
        # add sequence number to packet ..
        packet['sequence-no'] = self._sequence_no(interface_name)
        # ... and increment number locally
        self._sequence_no_inc(interface_name)
        packet['networks'] = list()
        packet['originator-addr-v4'] = self.conf_originator_addr_by_iface("v4", interface_name)
        for network in self._conf["networks"]:
            if network["proto"] == "v4":
                ipstr = "{}/{}".format(network["prefix"], network["prefix-len"])
                packet['networks'].append({ "v4-prefix" : ipstr })
        packet['routingpaths'] = dict()
       # if len(self.fib['high_bandwidth'])>0 or len(self.fib['low_loss'])>0:
        if len(self.fib['high_bandwidth'])>0 or len(self.fib['low_loss'])>0 or len(self.fib['bw_and_loss']) or len(self.fib['no_cost']) or len(self.fib['bw_and_cost'])>0:

           packet['routingpaths']=self.fib.copy()
        return packet


    def tx_route_packet(self):
        # depending on local information the route
        # packets must be generated for each interface
        for interface_name in self._rtd["interfaces"]:
            msg = self.create_routing_msg(interface_name)
            self.log.info(msg)
            v4_mcast_addr = self._conf["mcast-v4-tx-addr"]
            self._packet_tx_func(interface_name, "v4", v4_mcast_addr, msg,
                                 priv_data=self._packet_tx_func_priv_data)



    def tick(self):
        """ this function is called every second, DMPR will
            implement his own timer/timeout related functionality
            based on this ticker. This is not the most efficient
            way to implement timers but it is suitable to run in
            a real and simulated environment where time is discret.
            The argument time is a float value in seconds which should
            not used in a absolute manner, depending on environment this
            can be a unix timestamp or starting at 0 in simulation
            environments """
        if not self._started:
            # start() is not called, ignore this call
            return
        route_recalc_required = self._check_outdated_route_entries()
        if route_recalc_required:
            self._recalculate_routing_table()

        now = self._get_time(priv_data=self._get_time_priv_data)
        if now >= self._next_tx_time:
            self.tx_route_packet()
            self._calc_next_tx_time()
            self.transmitted_now = True
        else:
            self.transmitted_now = False


    def stop(self, init=False):
        self._started = False
        if not init:
            # this function is also called in the
            # constructor, so do not print stop when
            # we never started
            now = self._get_time(priv_data=self._get_time_priv_data)
            self.log.warning("stop DMPR core", time=now)
        self._routing_table = None
        self._next_tx_time = None


    def start(self):
        now = self._get_time(priv_data=self._get_time_priv_data)
        self.log.info("start DMPR core", time=now)
        assert(self._get_time)
        assert(self._routing_table_update_func)
        assert(self._packet_tx_func)
        assert(self._conf)
        assert(self._routing_table == None)
        self._init_runtime_data()
        self._calc_next_tx_time()
        self._started = True


    def restart(self):
        self.stop()
        self.start()


    def _init_runtime_data(self):
        self._rtd = dict()
        # init interface specific container data
        self._rtd["interfaces"] = dict()
        for interface in self._conf["interfaces"]:
            self._rtd["interfaces"][interface["name"]] = dict()
            self._rtd["interfaces"][interface["name"]]["sequence-no-tx"] = 0
            self._rtd["interfaces"][interface["name"]]["rx-msg-db"] = dict()
        self.fib = dict()
        self.fib['high_bandwidth'] = dict()
        self.fib['low_loss'] = dict()
        self.fib['bw_and_loss'] = dict()
        self.fib['no_cost'] = dict()
        self.fib['bw_and_cost'] = dict()


    def _sequence_no(self, interface_name):
        return self._rtd["interfaces"][interface_name]["sequence-no-tx"]


    def _sequence_no_inc(self, interface_name):
        self._rtd["interfaces"][interface_name]["sequence-no-tx"] += 1


    def _calc_next_tx_time(self):
        interval = int(self._conf["rtn-msg-interval"])
        if self._next_tx_time == None:
            # we start to the first time or after a
            # restart, so do not wait interval seconds, thisself._conf["id"]
            # is just silly, we want to join the network as early
            # as possible. But due to global synchronisation effects
            # we are kind and jitter at least some seconds
            interval = 0
        jitter = self._conf["rtn-msg-interval-jitter"]
        waittime = interval + random.randint(0, int(jitter))
        now = self._get_time(priv_data=self._get_time_priv_data)
        self._next_tx_time = now + waittime
        self.log.debug("schedule next transmission for {} seconds".format(self._next_tx_time), time=now)


    def _is_valid_interface(self, interface_name):
        found = False
        for interface in self._conf["interfaces"]:
            if interface_name == interface["name"]:
                found = True
        return found


    def _validate_rx_msg(self, msg, interface_name):
        ok = self._is_valid_interface(interface_name)
        if not ok:
            emsg  = "{} is not a configured, thus valid interface name, "
            emsg += "ignore packet for now"
            now = self._get_time(priv_data=self._get_time_priv_data)
            self.log.error(emsg.format(interface_name), time=now)
            return False
        if msg['id'] == self._conf['id']:
            emsg = "receive a message from ourself! id:{} == id:{}, ".format(msg['id'], self._conf['id'])
            emsg += " This means a) configration error (same id, or look problem"
            now = self._get_time(priv_data=self._get_time_priv_data)
            self.log.error(emsg, time=now)
            return False
        return True



    # FIXME: search log for update here
    def _cmp_dicts(self, dict1, dict2):
        if dict1 == None or dict2 == None: return False
        if type(dict1) is not dict or type(dict2) is not dict: return False
        shared_keys = set(dict2.keys()) & set(dict2.keys())
        if not len(shared_keys) == len(dict1.keys()) and len(shared_keys) == len(dict2.keys()):
            return False
        eq = True
        for key in dict1.keys():
            if type(dict1[key]) is dict:
                if key not in dict2:
                    return False
                else:
                    eq = eq and self._cmp_dicts(dict1[key], dict2[key])
            else:
                if key not in dict2:
                    return False
                else:
                    eq = eq and (dict1[key] == dict2[key])
        return eq


    def _cmp_packets(self, packet1, packet2):
        p1 = copy.deepcopy(packet1)
        p2 = copy.deepcopy(packet2)
        # some data may differ, but the content is identical,
        # zeroize them here out
        p1['sequence-no'] = 0
        p2['sequence-no'] = 0
        return self._cmp_dicts(p1, p2)


    def msg_rx(self, interface_name, msg):
        """ receive routing packet in json encoded
             data format """
        rxmsg = "rx route packet from {}, interface:{}, seq-no:{}"
        self.log.info(rxmsg.format(msg['id'], interface_name, msg['sequence-no']))
        ok = self._validate_rx_msg(msg, interface_name)
        if not ok:
            now = self._get_time(priv_data=self._get_time_priv_data)
            self.log.warning("packet corrupt, dropping it", time=now)
            return
        route_recalc_required = self._rx_save_routing_data(msg, interface_name)
        if route_recalc_required:
            self._recalculate_routing_table()


    def _rx_save_routing_data(self, msg, interface_name):
        route_recalc_required = True
        sender_id = msg["id"]
        if not sender_id in self._rtd["interfaces"][interface_name]["rx-msg-db"]:
            # new entry (never seen before) or outdated comes
            # back again
            self._rtd["interfaces"][interface_name]["rx-msg-db"][sender_id] = dict()
        else:
            # existing entry from neighbor
            last_msg = self._rtd["interfaces"][interface_name]["rx-msg-db"][sender_id]["msg"]
            seq_no_last = last_msg['sequence-no']
            seq_no_new  = msg['sequence-no']
            if seq_no_new <= seq_no_last:
                #print("receive duplicate or outdated route packet -> ignore it")
                route_recalc_required = False
                return route_recalc_required
            data_equal = self._cmp_packets(last_msg, msg)
            if data_equal:
                # packet is identical, we must save the last packet (think update sequence no)
                # but a route recalculation is not required
                route_recalc_required = False
        now = self._get_time(priv_data=self._get_time_priv_data)
        self._rtd["interfaces"][interface_name]["rx-msg-db"][sender_id]['rx-time'] = now
        self._rtd["interfaces"][interface_name]["rx-msg-db"][sender_id]['msg'] = msg
        self.log.info(self._rtd["interfaces"])
        return route_recalc_required


    def next_hop_ip_addr(self, proto, router_id, iface_name):
        """ return the IPv4/IPv6 address of the sender of an routing message """
        if iface_name not in self._rtd["interfaces"]:
            raise InternalException("interface not configured: {}".format(iface_name))
        if router_id not in self._rtd["interfaces"][iface_name]['rx-msg-db']:
            self.log.warning("cannot calculate next_hop_addr because router id is not in "
                             " databse (anymore!)? id:{}".format(router_id))
            return None
        msg = self._rtd["interfaces"][iface_name]['rx-msg-db'][router_id]['msg']
        if proto == 'v4':
            return msg['originator-addr-v4']
        if proto == 'v6':
            return msg['originator-addr-v6']
        raise InternalException("only v4 or v6 supported: {}".format(proto))


    def _recalculate_routing_table(self):
        now = self._get_time(priv_data=self._get_time_priv_data)
        self.log.info("recalculate routing table", time=now)
        # see _routing_table_update() this is how the routing
        # table should look like and saved under
        # self._routing_table
        # k1 and k2 value for bw and loss compound metric calculation
        #k1=k2=1 by default
        k1 = 1
        k2 = 100
        loss_flag = True
        bandwidth_flag = True
        cost_flag = True
        self._routing_table = dict()
        neigh_routing_paths = dict()
        self.fib = dict()
        self.fib['low_loss'] = dict()
        self.fib['high_bandwidth'] = dict()
        self.fib['bw_and_loss'] = dict()
        self.fib['no_cost'] = dict()
        self.fib['bw_and_cost'] = dict()
        self.fib['path_characteristics'] = dict()
        neigh_routing_paths = self._calc_neigh_routing_paths(neigh_routing_paths)
        if loss_flag==True:
           self._calc_fib_low_loss(neigh_routing_paths)
           self._calc_loss_routingtable()
        if bandwidth_flag==True:
           self._calc_fib_high_bandwidth(neigh_routing_paths)
           self._calc_bw_routingtable()
        if loss_flag==True and bandwidth_flag==True:
           self._calc_fib_bw_and_loss(neigh_routing_paths,k1,k2)
           self._calc_bw_and_loss_routingtable()
        if cost_flag==True:
           self._calc_fib_no_cost(neigh_routing_paths)
           self._calc_cost_routingtable()
        if cost_flag==True and bandwidth_flag==True:
           self._calc_fib_bw_and_cost(neigh_routing_paths)
           self._calc_bw_and_cost_routingtable()

        self.log.debug(self.fib)
        self.log.debug(self._routing_table)
        # routing table calculated, now inform our "parent"
        # about the new routing table
        self._routing_table_update()


    def _calc_neigh_routing_paths(self, neigh_routing_paths):
        neigh_routing_paths['neighs'] = dict()
        neigh_routing_paths['othernode_paths'] = dict()
        neigh_routing_paths['othernode_paths']['high_bandwidth'] = dict()
        neigh_routing_paths['othernode_paths']['low_loss'] = dict()
        neigh_routing_paths['othernode_paths']['no_cost'] = dict()
        neigh_routing_paths['othernode_paths']['bw_and_loss'] = dict()
        neigh_routing_paths['othernode_paths']['bw_and_cost'] = dict()
        for iface,iface_data in self._rtd["interfaces"].items():
            for sender_id,sender_data_raw in iface_data["rx-msg-db"].items():
                sender_data = dict()
                sender_data = sender_data_raw.copy()
                neigh_routing_paths = self._add_all_neighs(iface, iface_data,
                                                           sender_id, sender_data_raw,
                                                           neigh_routing_paths)
                if len(sender_data['msg']['routingpaths'])>0:
                   neigh_routing_paths = self._add_all_othernodes_loss(sender_id, sender_data,
                                                                       neigh_routing_paths)
                   neigh_routing_paths = self._add_all_othernodes_bw(sender_id, sender_data,
                                                                     neigh_routing_paths)
                   neigh_routing_paths = self._add_all_othernodes_bw_and_loss(sender_id, sender_data,
                                                                      neigh_routing_paths)
                   neigh_routing_paths = self._add_all_othernodes_no_cost(sender_id, sender_data,                                                                                                neigh_routing_paths)
                   neigh_routing_paths = self._add_all_othernodes_bw_and_cost(sender_id, sender_data,
                                                                      neigh_routing_paths)
        self.log.debug(neigh_routing_paths)
        return neigh_routing_paths


    def _add_all_neighs(self, iface, iface_data, sender_id, sender_data, neigh_routing_paths):
        found_neigh = False
        if len(neigh_routing_paths['neighs']) > 0:
           for neigh_id, neigh_data in neigh_routing_paths['neighs'].items():
               if neigh_id == sender_id:
                  path_found = False
                  for neigh_path in neigh_data['paths']["{}>{}".
                                                        format(self._conf["id"], neigh_id)]:
                      if neigh_path == iface:
                         path_found = True
                         break
                  if path_found == False:
                     neigh_data['paths']["{}>{}".
                                         format(self._conf["id"],neigh_id)].append(iface)
                  found_neigh = True
                  break
           if found_neigh == False:
              neigh_routing_paths = self._add_neigh_entries(iface, sender_id,
                                                            sender_data, neigh_routing_paths)
        else:
             neigh_routing_paths = self._add_neigh_entries(iface, sender_id,
                                                           sender_data, neigh_routing_paths)
        return neigh_routing_paths


    def _add_neigh_entries(self, iface, sender_id, sender_data, neigh_routing_paths):
        neigh_routing_paths['neighs'][sender_id] = {'next-hop': sender_id,
                                                    'networks': sender_data['msg']['networks'],
                                                    'paths':{"{}>{}".
                                                             format(self._conf["id"],sender_id):
                                                             [iface]}
                                                     }
        return neigh_routing_paths


    def _add_all_othernodes_bw(self, sender_id, sender_data, neigh_routing_paths):
        othernodes_bw = dict()
        othernodes_bw = neigh_routing_paths['othernode_paths']['high_bandwidth'].copy()
        if not sender_id in othernodes_bw:
           othernodes_bw[sender_id] = dict()
           othernodes_bw[sender_id]['path_characteristics'] = dict()
        else:
             self.log.info('updating high bandwidth routes to other nodes from the existing neighbour')
        sender_routeinfo = dict()
        sender_routeinfo = sender_data['msg']['routingpaths'].copy()
        othernodes_bw[sender_id] = sender_routeinfo['high_bandwidth']
        othernodes_bw[sender_id]['path_characteristics'] = sender_routeinfo['path_characteristics']
        neigh_routing_paths['othernode_paths']['high_bandwidth'] = othernodes_bw.copy()
        return neigh_routing_paths


    def _add_all_othernodes_loss(self, sender_id, sender_data, neigh_routing_paths):
        othernodes_loss = dict()
        othernodes_loss = neigh_routing_paths['othernode_paths']['low_loss'].copy()
        if not sender_id in othernodes_loss:
           othernodes_loss[sender_id] = dict()
           othernodes_loss[sender_id]['path_characteristics'] = dict()
        else:
             self.log.info('updating low loss routes to other nodes from the existing neighbour')
        sender_routeinfo = dict()
        sender_routeinfo = sender_data['msg']['routingpaths'].copy()
        othernodes_loss[sender_id] = sender_routeinfo['low_loss']
        othernodes_loss[sender_id]['path_characteristics'] = sender_routeinfo['path_characteristics']
        neigh_routing_paths['othernode_paths']['low_loss'] = othernodes_loss.copy()
        return neigh_routing_paths

    def _add_all_othernodes_bw_and_loss(self, sender_id, sender_data, neigh_routing_paths):
        othernodes_bw_and_loss = dict()
        othernodes_bw_and_loss = neigh_routing_paths['othernode_paths']['bw_and_loss'].copy()
        if not sender_id in othernodes_bw_and_loss:
           othernodes_bw_and_loss[sender_id] = dict()
           othernodes_bw_and_loss[sender_id]['path_characteristics'] = dict()
        else:
             self.log.info('updating bw and loss compound route to other nodes from the existing neighbour')
        sender_routeinfo = dict()
        sender_routeinfo = sender_data['msg']['routingpaths'].copy()
        othernodes_bw_and_loss[sender_id] = sender_routeinfo['bw_and_loss']
        othernodes_bw_and_loss[sender_id]['path_characteristics'] = sender_routeinfo['path_characteristics']
        neigh_routing_paths['othernode_paths']['bw_and_loss'] = othernodes_bw_and_loss.copy()
        return neigh_routing_paths

    def _add_all_othernodes_no_cost(self, sender_id, sender_data, neigh_routing_paths):
        othernodes_no_cost = dict()
        othernodes_no_cost = neigh_routing_paths['othernode_paths']['no_cost'].copy()
        if not sender_id in othernodes_no_cost:
           othernodes_no_cost[sender_id] = dict()
           othernodes_no_cost[sender_id]['path_characteristics'] = dict()
        else:
             self.log.info('updating no monetary cost route to other nodes from the existing neighbour')
        sender_routeinfo = dict()
        sender_routeinfo = sender_data['msg']['routingpaths'].copy()
        othernodes_no_cost[sender_id] = sender_routeinfo['no_cost']
        othernodes_no_cost[sender_id]['path_characteristics'] = sender_routeinfo['path_characteristics']
        neigh_routing_paths['othernode_paths']['no_cost'] = othernodes_no_cost.copy()
        return neigh_routing_paths

    def _add_all_othernodes_bw_and_cost(self, sender_id, sender_data, neigh_routing_paths):
        othernodes_bw_and_cost = dict()
        othernodes_bw_and_cost = neigh_routing_paths['othernode_paths']['bw_and_cost'].copy()
        if not sender_id in othernodes_bw_and_cost:
           othernodes_bw_and_cost[sender_id] = dict()
           othernodes_bw_and_cost[sender_id]['path_characteristics'] = dict()
        else:
             self.log.info('updating filtered bandwidth and cost route to other nodes from the existing neighbour')
        sender_routeinfo = dict()
        sender_routeinfo = sender_data['msg']['routingpaths'].copy()
        othernodes_bw_and_cost[sender_id] = sender_routeinfo['bw_and_cost']
        othernodes_bw_and_cost[sender_id]['path_characteristics'] = sender_routeinfo['path_characteristics']
        neigh_routing_paths['othernode_paths']['bw_and_cost'] = othernodes_bw_and_cost.copy()
        return neigh_routing_paths


    def _calc_fib_low_loss(self, neigh_routing_paths):
        weigh_loss = dict()
        compressedloss = dict()
        for neigh_id, neigh_data in neigh_routing_paths['neighs'].items():
            weigh_loss = self._loss_path_compression(neigh_data)
            compressedloss = self.add_loss_entry(neigh_id, neigh_data,
                                                 weigh_loss, compressedloss)
        self.fib['low_loss'] = compressedloss.copy()
        if len(neigh_routing_paths['othernode_paths']['low_loss']) > 0:
           self._calc_shortestloss_path(neigh_routing_paths)
        self._map_path_characteristics_loss(neigh_routing_paths)
        self._add_self_to_neigh_losspathnumber()
        self._add_lossweight_to_dest()


    def _calc_fib_high_bandwidth(self, neigh_routing_paths):
        weigh_bandwidth = dict()
        compressedBW = dict()
        for neigh_id, neigh_data in neigh_routing_paths['neighs'].items():
            weigh_bandwidth = self._bandwidth_path_compression(neigh_data)
            compressedBW = self.add_bandwidth_entry(neigh_id, neigh_data,
                                                    weigh_bandwidth, compressedBW)
        self.fib['high_bandwidth'] = compressedBW.copy()
        if len(neigh_routing_paths['othernode_paths']['high_bandwidth']) > 0:
           self._calc_widestBW_path(neigh_routing_paths)
        self._map_path_characteristics_BW(neigh_routing_paths)
        self._add_self_to_neigh_bandwidthpathnumber()
        self._add_bandwidthweight_to_dest()

    def _calc_fib_bw_and_loss(self, neigh_routing_paths,k1,k2):
        weigh_bw_and_loss = dict()
        compressedBWLoss = dict()
        for neigh_id, neigh_data in neigh_routing_paths['neighs'].items():
            weigh_bw_and_loss = self._bw_and_loss_path_compression(neigh_data,k1,k2)
            compressedBWLoss = self.add_bw_and_loss_entry(neigh_id, neigh_data,
                                                          weigh_bw_and_loss, compressedBWLoss)
        self.fib['bw_and_loss'] = compressedBWLoss.copy()
        if len(neigh_routing_paths['othernode_paths']['bw_and_loss']) > 0:
           self._calc_CompoundBWLoss_path(neigh_routing_paths)
        self._map_path_characteristics_BW_and_loss(neigh_routing_paths)
        self._add_self_to_neigh_BW_and_loss_pathnumber()
        self._add_BW_and_lossweight_to_dest(k1, k2)

    def _calc_fib_no_cost(self, neigh_routing_paths):
        weigh_cost = dict()
        compressedCost = dict()
        for neigh_id, neigh_data in neigh_routing_paths['neighs'].items():
            weigh_cost = self._no_cost_path_compression(neigh_data)
            if len(weigh_cost) > 0:
               compressedCost = self.add_cost_entry(neigh_id, neigh_data,
                                                    weigh_cost, compressedCost)
        self.fib['no_cost'] = compressedCost.copy()
        if len(neigh_routing_paths['othernode_paths']['no_cost']) > 0:
           self._calc_nocost_path(neigh_routing_paths)
        self._map_path_characteristics_cost(neigh_routing_paths)
        self._add_self_to_neigh_cost_pathnumber()
        self._add_costweight_to_dest()

    def _calc_fib_bw_and_cost(self, neigh_routing_paths):
        weigh_bw_and_cost = dict()
        compressedBWCost = dict()
        for neigh_id, neigh_data in neigh_routing_paths['neighs'].items():
            weigh_bw_and_cost = self._bw_and_cost_path_compression(neigh_data)
            if len(weigh_bw_and_cost) >0:
               compressedBWCost = self.add_bw_and_cost_entry(neigh_id, neigh_data,
                                                          weigh_bw_and_cost, compressedBWCost)
        self.fib['bw_and_cost'] = compressedBWCost.copy()
        if len(neigh_routing_paths['othernode_paths']['bw_and_cost']) > 0:
           self._calc_filteredBWCost_path(neigh_routing_paths)
        self._map_path_characteristics_BW_and_cost(neigh_routing_paths)
        self._add_self_to_neigh_BW_and_cost_pathnumber()
        self._add_BW_and_costweight_to_dest()

    def _loss_path_compression(self, neigh_data):
        loss_dict = dict()
        for neigh_path_key,neigh_paths_name in neigh_data['paths'].items():
            for neigh_iface_name in neigh_paths_name:
                for iface in self._conf['interfaces']:
                    if iface['name'] == neigh_iface_name:
                       loss = iface['link-characteristics']['loss']
                       if len(loss_dict) > 0:
                          for iface_name, iface_loss in loss_dict.items():
                              if loss < iface_loss:
                                 loss_dict = dict()
                                 loss_dict[iface['name']] = loss
                       else:
                            loss_dict[iface['name']] = loss
                       break
        return loss_dict


    def _bandwidth_path_compression(self, neigh_data):
        bandwidth_dict = dict()
        for neigh_path_key, neigh_paths_name in neigh_data['paths'].items():
            for neigh_iface_name in neigh_paths_name:
                for iface in self._conf['interfaces']:
                    if iface['name'] == neigh_iface_name:
                       bw = iface['link-characteristics']['bandwidth']
                       if len(bandwidth_dict)>0:
                          for iface_name, iface_bw in bandwidth_dict.items():
                              if bw > iface_bw:
                                 bandwidth_dict=dict()
                                 bandwidth_dict[iface['name']] = bw
                       else:
                            bandwidth_dict[iface['name']] = bw
                       break
        return bandwidth_dict


    def _bw_and_loss_path_compression(self, neigh_data, k1, k2):
        bw_and_loss_dict = dict()
        for neigh_path_key,neigh_paths_name in neigh_data['paths'].items():
            for neigh_iface_name in neigh_paths_name:
                for iface in self._conf['interfaces']:
                     if iface['name'] == neigh_iface_name:
                        loss = iface['link-characteristics']['loss']
                        bw = iface['link-characteristics']['bandwidth']
                        bw_and_loss = ((k1*(10000000/bw))+(k2*loss))
                        if len(bw_and_loss_dict) > 0:
                           for iface_name, iface_bw_and_loss in bw_and_loss_dict.items():
                               if bw_and_loss < iface_bw_and_loss:
                                  bw_and_loss_dict = dict()
                                  bw_and_loss_dict[iface['name']] = bw_and_loss
                        else:
                             bw_and_loss_dict[iface['name']] = bw_and_loss
                        break
        return bw_and_loss_dict

    def _no_cost_path_compression(self, neigh_data):
        no_cost_dict = dict()
        for neigh_path_key,neigh_paths_name in neigh_data['paths'].items():
            for neigh_iface_name in neigh_paths_name:
                for iface in self._conf['interfaces']:
                    if iface['name'] == neigh_iface_name:
                       cost = iface['link-characteristics']['cost']
                       #if len(no_cost_dict) > 0:
                         # for iface_name, iface_cost in no_cost_dict.items():
                           #   if cost < iface_cost:
                            #     no_cost_dict = dict()
                             #    cost_dict[iface['name']] = cost
                       #else:
                       if cost == 0:
                          no_cost_dict[iface['name']] = cost
                       break
        return no_cost_dict

    def _bw_and_cost_path_compression(self, neigh_data):
        bw_and_cost_dict = dict()
        for neigh_path_key,neigh_paths_name in neigh_data['paths'].items():
            for neigh_iface_name in neigh_paths_name:
                for iface in self._conf['interfaces']:
                    if iface['name'] == neigh_iface_name:
                       cost = iface['link-characteristics']['cost']
                       if cost == 0:
                          bw = iface['link-characteristics']['bandwidth']
                          if len(bw_and_cost_dict) > 0:
                             for iface_name, iface_bw in bw_and_cost_dict.items():
                                 if bw > iface_bw:
                                    bw_and_cost_dict = dict()
                                    bw_and_cost_dict[iface['name']] = bw
                          else:
                               bw_and_cost_dict[iface['name']] = bw
                          break
        return bw_and_cost_dict

    def add_loss_entry(self, neigh_id, neigh_data, weigh_loss, compressedloss):
        route = "{}>{}".format(self._conf["id"], neigh_id)
        compressedloss[neigh_id] = {'next-hop':neigh_data['next-hop'],
                                    'networks':neigh_data['networks']
                                   }
        for iface, iface_loss in weigh_loss.items():
            compressedloss[neigh_id]['weight'] = iface_loss
            compressedloss[neigh_id]['paths'] = dict()
            compressedloss[neigh_id]['paths'][route] = iface
        return compressedloss


    def add_bandwidth_entry(self, neigh_id, neigh_data, weigh_bandwidth, compressedBW):
        route = "{}>{}".format(self._conf["id"], neigh_id)
        compressedBW[neigh_id] = {'next-hop':neigh_data['next-hop'],
                                  'networks':neigh_data['networks']
                                 }
        for iface, iface_bw in weigh_bandwidth.items():
            compressedBW[neigh_id]['weight'] = iface_bw
            compressedBW[neigh_id]['paths'] = dict()
            compressedBW[neigh_id]['paths'][route] = iface
        return compressedBW


    def add_bw_and_loss_entry(self, neigh_id, neigh_data, weigh_bw_and_loss, compressedBWLoss):
        route = "{}>{}".format(self._conf["id"], neigh_id)
        compressedBWLoss[neigh_id] = {'next-hop':neigh_data['next-hop'],
                                      'networks':neigh_data['networks']
                                     }
        for iface, iface_bw_and_loss in weigh_bw_and_loss.items():
            compressedBWLoss[neigh_id]['weight'] = iface_bw_and_loss
            compressedBWLoss[neigh_id]['paths'] = dict()
            compressedBWLoss[neigh_id]['paths'][route] = iface
        return compressedBWLoss

    def add_cost_entry(self, neigh_id, neigh_data, weigh_cost, compressedCost):
        route = "{}>{}".format(self._conf["id"], neigh_id)
        compressedCost[neigh_id] = {'next-hop':neigh_data['next-hop'],
                                    'networks':neigh_data['networks']
                                   }
        for iface, iface_cost in weigh_cost.items():
            compressedCost[neigh_id]['weight'] = iface_cost
            compressedCost[neigh_id]['paths'] = dict()
            compressedCost[neigh_id]['paths'][route] = iface
        return compressedCost

    def add_bw_and_cost_entry(self, neigh_id, neigh_data, weigh_bw_and_cost, compressedBWCost):
        route = "{}>{}".format(self._conf["id"], neigh_id)
        compressedBWCost[neigh_id] = {'next-hop':neigh_data['next-hop'],
                                     'networks':neigh_data['networks']
                                     }
        for iface, iface_bw_and_cost in weigh_bw_and_cost.items():
            compressedBWCost[neigh_id]['weight'] = iface_bw_and_cost
            compressedBWCost[neigh_id]['paths'] = dict()
            compressedBWCost[neigh_id]['paths'][route] = iface
        return compressedBWCost

    def _calc_shortestloss_path(self, neigh_routing_paths):
        path_weight = dict()
        for other_id, other_data in neigh_routing_paths['othernode_paths']['low_loss'].items():
            for dest_id, dest_data in other_data.items():
                if dest_id != 'path_characteristics':
                   if dest_id == self._conf["id"]:
                      self.log.info('ignore self routing')
                   else:
                        loss_to_neigh = int(self.fib['low_loss'][other_id]['weight'])
                        weight_update = int(dest_data['weight']) + loss_to_neigh
                        loop_found = False
                        for path, path_loss in dest_data['paths'].items():# Each path for example '1>2'
                            id1_in_path = path[0]
                            id2_in_path = path[2]
                            if id1_in_path == self._conf["id"] or id2_in_path == self._conf["id"]:
                               loop_found = True
                               self.log.info('self_id in the path so avoiding looping')
                               break
                        if loop_found==False:
                            self.log.info('No loop will occur in this path')
                            self.add_shortestloss_path(weight_update, other_id, dest_id, dest_data)


    def add_shortestloss_path(self, weight_update, other_id, dest_id, dest_data):
        if not dest_id in self.fib['low_loss']:
           self.log.info('it is a new entry to destination')
           self.fib['low_loss'][dest_id] = dict()
           self._map_loss_values(other_id, weight_update, dest_id, dest_data)
        else:
             self.log.info('updating existing destination entry in fib')
             if weight_update < self.fib['low_loss'][dest_id]['weight']:
                self._map_loss_values(other_id, weight_update, dest_id, dest_data)


    def _map_loss_values(self, other_id, weight_update, dest_id, dest_data):
        data = self.fib['low_loss'][dest_id]
        data['networks'] = list()
        data['paths'] = dict()
        data['weight'] = weight_update
        data['next-hop'] = other_id
        data['networks'] = dest_data['networks'].copy()
        data['paths'] = dest_data['paths'].copy()


    def _calc_widestBW_path(self, neigh_routing_paths):
        path_weight = dict()
        for other_id, other_data in neigh_routing_paths['othernode_paths']['high_bandwidth'].items():
            for dest_id, dest_data in other_data.items():
                if dest_id != 'path_characteristics':
                   if dest_id == self._conf["id"]:
                      self.log.info('ignore self routing')
                   else:
                        bw_to_neigh = int(self.fib['high_bandwidth'][other_id]['weight'])
                        weight_update = int(dest_data['weight']) + bw_to_neigh
                        loop_found = False
                        for path, path_loss in dest_data['paths'].items():
                            id1_in_path = path[0]
                            id2_in_path = path[2]
                            if id1_in_path == self._conf["id"] or id2_in_path == self._conf["id"]:
                               loop_found = True
                               self.log.info('self_id in the path so avoiding looping')
                               break
                        if loop_found==False:
                           self.log.info('No loop will occur in this path')
                           self.add_widestBW_path(weight_update, other_id, dest_id, dest_data)


    def add_widestBW_path(self, weight_update, other_id, dest_id, dest_data):
        if not dest_id in self.fib['high_bandwidth']:
           self.log.info('it is a new entry to destination')
           self.fib['high_bandwidth'][dest_id] = dict()
           self._map_BW_values(other_id, weight_update, dest_id, dest_data)
        else:
             if weight_update < self.fib['high_bandwidth'][dest_id]['weight']:
                self.log.info('updating existing destination entry in fib')
                self._map_BW_values(other_id, weight_update, dest_id, dest_data)


    def _map_BW_values(self, other_id, weight_update, dest_id, dest_data):
        data = self.fib['high_bandwidth'][dest_id]
        data['networks'] = list()
        data['paths'] = dict()
        data['next-hop'] = other_id
        data['weight'] = weight_update
        data['networks'] = dest_data['networks'].copy()
        data['paths'] = dest_data['paths'].copy()


    def _calc_CompoundBWLoss_path(self, neigh_routing_paths):
        path_weight = dict()
        for other_id, other_data in neigh_routing_paths['othernode_paths']['bw_and_loss'].items():
            for dest_id, dest_data in other_data.items():
                if dest_id != 'path_characteristics':
                   if dest_id == self._conf["id"]:
                      self.log.info('ignore self routing')
                   else:
                        bw_loss_to_neigh = int(self.fib['bw_and_loss'][other_id]['weight'])
                        weight_update = int(dest_data['weight']) + bw_loss_to_neigh
                        loop_found = False
                        for path, path_bw_and_loss in dest_data['paths'].items():
                            id1_in_path = path[0]
                            id2_in_path = path[2]
                            if id1_in_path == self._conf["id"] or id2_in_path == self._conf["id"]:
                               loop_found = True
                               self.log.info('self_id in the path so avoiding looping')
                               break
                        if loop_found==False:
                           self.log.info('No loop will occur in this path')
                           self.add_CompoundBWLoss_path(weight_update, other_id, dest_id, dest_data)


    def add_CompoundBWLoss_path(self, weight_update, other_id, dest_id, dest_data):
        if not dest_id in self.fib['bw_and_loss']:
           self.log.info('it is a new entry to destination')
           self.fib['bw_and_loss'][dest_id] = dict()
           self._map_BWLoss_values(other_id, weight_update, dest_id, dest_data)
        else:
             if weight_update < self.fib['bw_and_loss'][dest_id]['weight']:
                self.log.info('updating existing destination entry in fib')
                self._map_BWLoss_values(other_id, weight_update, dest_id, dest_data)


    def _map_BWLoss_values(self, other_id, weight_update, dest_id, dest_data):
        data = self.fib['bw_and_loss'][dest_id]
        data['networks'] = list()
        data['paths'] = dict()
        data['next-hop'] = other_id
        data['weight'] = weight_update
        data['networks'] = dest_data['networks'].copy()
        data['paths'] = dest_data['paths'].copy()

    def _calc_nocost_path(self, neigh_routing_paths):
        path_weight = dict()
        for other_id, other_data in neigh_routing_paths['othernode_paths']['no_cost'].items():
            for dest_id, dest_data in other_data.items():
                if dest_id != 'path_characteristics':
                   if dest_id == self._conf["id"]:
                      self.log.info('ignore self routing')
                   else:
                        cost_to_neigh = int(self.fib['no_cost'][other_id]['weight'])
                        weight_update = int(dest_data['weight']) + cost_to_neigh
                        loop_found = False
                        for path, path_cost in dest_data['paths'].items():
                            id1_in_path = path[0]
                            id2_in_path = path[2]
                            if id1_in_path == self._conf["id"] or id2_in_path == self._conf["id"]:
                               loop_found = True
                               self.log.info('self_id in the path so avoiding looping')
                               break
                        if loop_found==False:
                           self.log.info('No loop will occur in this path')
                           self.add_nocost_path(weight_update, other_id, dest_id, dest_data)


    def add_nocost_path(self, weight_update, other_id, dest_id, dest_data):
        if not dest_id in self.fib['no_cost']:
           self.log.info('it is a new entry to destination')
           self.fib['no_cost'][dest_id] = dict()
           self._map_cost_values(other_id, weight_update, dest_id, dest_data)
        else:
             if weight_update < self.fib['no_cost'][dest_id]['weight']:
                self.log.info('updating existing destination entry in fib')
                self._map_cost_values(other_id, weight_update, dest_id, dest_data)


    def _map_cost_values(self, other_id, weight_update, dest_id, dest_data):
        data = self.fib['no_cost'][dest_id]
        data['networks'] = list()
        data['paths'] = dict()
        data['next-hop'] = other_id
        data['weight'] = weight_update
        data['networks'] = dest_data['networks'].copy()
        data['paths'] = dest_data['paths'].copy()

    def _calc_filteredBWCost_path(self, neigh_routing_paths):
        path_weight = dict()
        for other_id, other_data in neigh_routing_paths['othernode_paths']['bw_and_cost'].items():
            for dest_id, dest_data in other_data.items():
                if dest_id != 'path_characteristics':
                    if dest_id == self._conf["id"]:
                       self.log.info('ignore self routing')
                    else:
                         bw_cost_to_neigh = int(self.fib['bw_and_cost'][other_id]['weight'])
                         weight_update = int(dest_data['weight']) + bw_cost_to_neigh
                         loop_found = False
                         for path, path_cost in dest_data['paths'].items():
                             id1_in_path = path[0]
                             id2_in_path = path[2]
                             if id1_in_path == self._conf["id"] or id2_in_path == self._conf["id"]:
                                loop_found = True
                                self.log.info('self_id in the path so avoiding looping')
                                break
                         if loop_found==False:
                            self.log.info('No loop will occur in this path')
                            self.add_bw_and_cost_path(weight_update, other_id, dest_id, dest_data)


    def add_bw_and_cost_path(self, weight_update, other_id, dest_id, dest_data):
        if not dest_id in self.fib['bw_and_cost']:
           self.log.info('it is a new entry to destination')
           self.fib['bw_and_cost'][dest_id] = dict()
           self._map_bw_cost_values(other_id, weight_update, dest_id, dest_data)
        else:
             if weight_update < self.fib['bw_and_cost'][dest_id]['weight']:
                self.log.info('updating existing destination entry in fib')
                self._map_bw_cost_values(other_id, weight_update, dest_id, dest_data)


    def _map_bw_cost_values(self, other_id, weight_update, dest_id, dest_data):
        data = self.fib['bw_and_cost'][dest_id]
        data['networks'] = list()
        data['paths'] = dict()
        data['next-hop'] = other_id
        data['weight'] = weight_update
        data['networks'] = dest_data['networks'].copy()
        data['paths'] = dest_data['paths'].copy()

    def _map_path_characteristics_loss(self, neigh_routing_paths):
        path_num = 1
        for dest_id, dest_data in self.fib['low_loss'].items():
            next_hop = dest_data['next-hop']
            path_num_found = False
            if dest_id != next_hop:
               self.log.info('This is not neighbour destination-loss')
               for path, path_number in dest_data['paths'].items():
                   path_info = dict()
                   path_info = neigh_routing_paths['othernode_paths']['low_loss'][next_hop]['path_characteristics']
                   for path_type, path_data in path_info.items():
                       if path_number == path_type:
                          path_num_found = True
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found == True:
                      dest_data['paths'][path] = path_num_new
            if dest_id == next_hop:
               self.log.info('This is neighbour destination-loss')
               for path, path_number in dest_data['paths'].items():
                   for iface in self._conf['interfaces']:
                       if iface['name'] == path_number:
                          path_num_found = True
                          path_data = dict()
                          path_data['loss'] = iface['link-characteristics']['loss']
                          path_data['bandwidth'] = iface['link-characteristics']['bandwidth']
                          path_data['cost'] = iface['link-characteristics']['cost']
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new


    def _map_path_characteristics_BW(self, neigh_routing_paths):
        path_num = 1
        for dest_id, dest_data in self.fib['high_bandwidth'].items():
            next_hop = dest_data['next-hop']
            path_num_found = False
            if dest_id != next_hop:
               self.log.info('This is not neighbour destination-BW')
               for path, path_number in dest_data['paths'].items():
                   path_info = dict()
                   path_info = neigh_routing_paths['othernode_paths']['high_bandwidth'][next_hop]['path_characteristics']
                   for path_type, path_data in path_info.items():
                       if path_number == path_type:
                          path_num_found = True
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new
            if dest_id == next_hop:
                 self.log.info('This is neighbour destination-BW')
                 for path, path_number in dest_data['paths'].items():
                     for iface in self._conf['interfaces']:
                         if iface['name']==path_number:
                            path_num_found = True
                            path_data = dict()
                            path_data['loss'] = iface['link-characteristics']['loss']
                            path_data['bandwidth'] = iface['link-characteristics']['bandwidth']
                            path_data['cost'] = iface['link-characteristics']['cost']
                            path_num_new = self._map_path_number(path_data, path_num)
                            break
                     if path_num_found==True:
                        dest_data['paths'][path] = path_num_new


    def _map_path_characteristics_BW_and_loss(self, neigh_routing_paths):
        path_num = 1
        for dest_id, dest_data in self.fib['bw_and_loss'].items():
            next_hop = dest_data['next-hop']
            path_num_found = False
            if dest_id != next_hop:
               self.log.info('This is not neighbour destination-BWLoss')
               for path, path_number in dest_data['paths'].items():
                   path_info = dict()
                   path_info = neigh_routing_paths['othernode_paths']['bw_and_loss'][next_hop]['path_characteristics']
                   for path_type, path_data in path_info.items():
                       if path_number == path_type:
                          path_num_found = True
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new
            if dest_id == next_hop:
               self.log.info('This is neighbour destination-BWLoss')
               for path, path_number in dest_data['paths'].items():
                   for iface in self._conf['interfaces']:
                       if iface['name']==path_number:
                          path_num_found = True
                          path_data = dict()
                          path_data['loss'] = iface['link-characteristics']['loss']
                          path_data['bandwidth'] = iface['link-characteristics']['bandwidth']
                          path_data['cost'] = iface['link-characteristics']['cost']
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new

    def _map_path_characteristics_cost(self, neigh_routing_paths):
        path_num = 1
        self.log.debug(self.fib)
        for dest_id, dest_data in self.fib['no_cost'].items():
            next_hop = dest_data['next-hop']
            path_num_found = False
            if dest_id != next_hop:
               self.log.info('This is not neighbour destination-Cost')
               for path, path_number in dest_data['paths'].items():
                   path_info = dict()
                   path_info = neigh_routing_paths['othernode_paths']['no_cost'][next_hop]['path_characteristics']
                   for path_type, path_data in path_info.items():
                       if path_number == path_type:
                          path_num_found = True
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new
            if dest_id == next_hop:
               self.log.info('This is neighbour destination-Cost')
               self.log.debug(dest_data['paths'])
               for path, path_number in dest_data['paths'].items():
                   for iface in self._conf['interfaces']:
                       if iface['name']==path_number:
                          path_num_found = True
                          path_data = dict()
                          path_data['loss'] = iface['link-characteristics']['loss']
                          path_data['bandwidth'] = iface['link-characteristics']['bandwidth']
                          path_data['cost'] = iface['link-characteristics']['cost']
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new


    def _map_path_characteristics_BW_and_cost(self, neigh_routing_paths):
        path_num = 1
        for dest_id, dest_data in self.fib['bw_and_cost'].items():
            next_hop = dest_data['next-hop']
            path_num_found = False
            if dest_id != next_hop:
               self.log.info('This is not neighbour destination-BWCost')
               for path, path_number in dest_data['paths'].items():
                   path_info = dict()
                   path_info = neigh_routing_paths['othernode_paths']['bw_and_cost'][next_hop]['path_characteristics']
                   for path_type, path_data in path_info.items():
                       if path_number == path_type:
                          path_num_found = True
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new
            if dest_id == next_hop:
               self.log.info('This is neighbour destination-BWCost')
               for path, path_number in dest_data['paths'].items():
                   for iface in self._conf['interfaces']:
                       if iface['name']==path_number:
                          path_num_found = True
                          path_data = dict()
                          path_data['loss'] = iface['link-characteristics']['loss']
                          path_data['cost'] = iface['link-characteristics']['cost']
                          path_data['bandwidth'] = iface['link-characteristics']['bandwidth']
                          path_num_new = self._map_path_number(path_data, path_num)
                          break
                   if path_num_found==True:
                      dest_data['paths'][path] = path_num_new


    def _map_path_number(self, path_data, path_num):
        path_char_found = False
        self.log.debug(self.fib['path_characteristics'])
        for fib_path_name, fib_path_data in self.fib['path_characteristics'].items():
            if (path_data['loss']==fib_path_data['loss']) and (path_data['bandwidth']==fib_path_data['bandwidth']) and (path_data['cost']==fib_path_data['cost']) :
               self.log.info('This is already existing path cahracteristic')
               path_num_new = fib_path_name
               path_char_found = True
               break
        if path_char_found==False:
           while True:
                 if not str(path_num) in self.fib['path_characteristics']:
                    path_num_new = str(path_num)
                    self.log.info('This path number is unique')
                    break
                 else:
                      path_num+=1
           self.fib['path_characteristics'][path_num_new] = path_data
        return path_num_new


    def _add_self_to_neigh_losspathnumber(self):
        for i in range(2):
            for dest_id, dest_data in self.fib['low_loss'].items():
                next_hop = dest_data['next-hop']
                if dest_id != next_hop:
                   for path, path_num in self.fib['low_loss'][next_hop]['paths'].items():
                       self.fib['low_loss'][dest_id]['paths'][path] = path_num


    def _add_self_to_neigh_bandwidthpathnumber(self):
        for i in range(2):
            for dest_id, dest_data in self.fib['high_bandwidth'].items():
                next_hop = dest_data['next-hop']
                if dest_id != next_hop:
                   for path, path_num in self.fib['high_bandwidth'][next_hop]['paths'].items():
                       self.fib['high_bandwidth'][dest_id]['paths'][path] = path_num


    def _add_self_to_neigh_BW_and_loss_pathnumber(self):
        for i in range(2):
            for dest_id, dest_data in self.fib['bw_and_loss'].items():
                next_hop = dest_data['next-hop']
                if dest_id != next_hop:
                   for path, path_num in self.fib['bw_and_loss'][next_hop]['paths'].items():
                       self.fib['bw_and_loss'][dest_id]['paths'][path] = path_num


    def _add_self_to_neigh_cost_pathnumber(self):
        for i in range(2):
            for dest_id, dest_data in self.fib['no_cost'].items():
                next_hop = dest_data['next-hop']
                if dest_id != next_hop:
                   for path, path_num in self.fib['no_cost'][next_hop]['paths'].items():
                       self.fib['no_cost'][dest_id]['paths'][path] = path_num


    def _add_self_to_neigh_BW_and_cost_pathnumber(self):
        for i in range(2):
            for dest_id, dest_data in self.fib['bw_and_cost'].items():
                next_hop = dest_data['next-hop']
                if dest_id != next_hop:
                   for path, path_num in self.fib['bw_and_cost'][next_hop]['paths'].items():
                       self.fib['bw_and_cost'][dest_id]['paths'][path] = path_num


    def _add_lossweight_to_dest(self):
        for dest_id, dest_data in self.fib['low_loss'].items():
            self.fib['low_loss'][dest_id]['weight'] = 0
            for path, path_num in dest_data['paths'].items():
                for path_fib, path_data_fib in self.fib['path_characteristics'].items():
                    if path_num == path_fib:
                       weight_pre = self.fib['low_loss'][dest_id]['weight']
                       self.fib['low_loss'][dest_id]['weight'] = weight_pre + path_data_fib['loss']
                       break


    def _add_bandwidthweight_to_dest(self):
        for dest_id, dest_data in self.fib['high_bandwidth'].items():
            self.fib['high_bandwidth'][dest_id]['weight'] = 0
            for path, path_num in dest_data['paths'].items():
                for path_fib, path_data_fib in self.fib['path_characteristics'].items():
                    if path_num == path_fib:
                       weight_pre = self.fib['high_bandwidth'][dest_id]['weight']
                       self.fib['high_bandwidth'][dest_id]['weight'] = weight_pre + path_data_fib['bandwidth']
                       break


    def _add_BW_and_lossweight_to_dest(self, k1, k2):
        for dest_id, dest_data in self.fib['bw_and_loss'].items():
            self.fib['bw_and_loss'][dest_id]['weight'] = 0
            for path, path_num in dest_data['paths'].items():
                for path_fib, path_data_fib in self.fib['path_characteristics'].items():
                    if path_num == path_fib:
                       weight_pre = self.fib['bw_and_loss'][dest_id]['weight']
                       bw = path_data_fib['bandwidth']
                       loss = path_data_fib['loss']
                       compound_metric = ((k1*(10000000/bw))+(k2*loss))
                       self.fib['bw_and_loss'][dest_id]['weight'] = weight_pre + compound_metric
                       break

    def _add_costweight_to_dest(self):
        for dest_id, dest_data in self.fib['no_cost'].items():
            self.fib['no_cost'][dest_id]['weight'] = 0
            for path, path_num in dest_data['paths'].items():
                for path_fib, path_data_fib in self.fib['path_characteristics'].items():
                    if path_num == path_fib:
                       weight_pre = self.fib['no_cost'][dest_id]['weight']
                       self.fib['no_cost'][dest_id]['weight'] = weight_pre + path_data_fib['cost']
                       break

    def _add_BW_and_costweight_to_dest(self):
        for dest_id, dest_data in self.fib['bw_and_cost'].items():
            self.fib['bw_and_cost'][dest_id]['weight'] = 0
            for path, path_num in dest_data['paths'].items():
                for path_fib, path_data_fib in self.fib['path_characteristics'].items():
                    if path_num == path_fib:
                       weight_pre = self.fib['bw_and_cost'][dest_id]['weight']
                       self.fib['bw_and_cost'][dest_id]['weight'] = weight_pre + path_data_fib['bandwidth']
                       break


    def _calc_loss_routingtable(self):
        self._routing_table['lowest-loss']=list()
        for dest_id, dest_data in self.fib['low_loss'].items():
            for network in dest_data['networks']:
                loss_entry = dict()
                for prefix_type, prefix_ip in network.items():
                    loss_entry['proto'] = "v4"
                    ip_pref_len = prefix_ip.split("/")
                    loss_entry['prefix'] = ip_pref_len[0]
                    loss_entry['prefix-len'] = ip_pref_len[1]
                search_key = '{}>{}'.format(self._conf["id"], dest_data['next-hop'])
                for path, path_num in dest_data['paths'].items():
                    if path == search_key:
                       for fib_path, fib_path_data in self.fib['path_characteristics'].items():
                           if fib_path == path_num:
                              path_found = False
                              for iface in self._conf['interfaces']:
                                  path_char = dict()
                                  path_char = iface['link-characteristics']
                                  if path_char['loss']==fib_path_data['loss'] and path_char['bandwidth']==fib_path_data['bandwidth']:
                                     path_found = True
                                     loss_entry['interface'] = iface['name']
                                     break
                              if path_found==True:
                                 break
                       break
                loss_entry['next-hop'] = self.next_hop_ip_addr(loss_entry['proto'], dest_data['next-hop'], loss_entry['interface'])
                self._routing_table['lowest-loss'].append(loss_entry)


    def _calc_bw_routingtable(self):
        self._routing_table['highest-bandwidth']=list()
        for dest_id, dest_data in self.fib['high_bandwidth'].items():
            for network in dest_data['networks']:
                bw_entry=dict()
                for prefix_type, prefix_ip in network.items():
                    bw_entry['proto'] = "v4"
                    ip_pref_len = prefix_ip.split("/")
                    bw_entry['prefix'] = ip_pref_len[0]
                    bw_entry['prefix-len'] = ip_pref_len[1]
                search_key='{}>{}'.format(self._conf["id"], dest_data['next-hop'])
                for path, path_num in dest_data['paths'].items():
                   if path == search_key:
                      for fib_path, fib_path_data in self.fib['path_characteristics'].items():
                          if fib_path == path_num:
                             path_found = False
                             for iface in self._conf['interfaces']:
                                 path_char = dict()
                                 path_char = iface['link-characteristics']
                                 if path_char['loss']==fib_path_data['loss'] and path_char['bandwidth']==fib_path_data['bandwidth']:
                                    path_found = True
                                    bw_entry['interface'] = iface['name']
                                    break
                             if path_found==True:
                                break
                      break
                bw_entry['next-hop'] = self.next_hop_ip_addr(bw_entry['proto'], dest_data['next-hop'], bw_entry['interface'])
                self._routing_table['highest-bandwidth'].append(bw_entry)


    def _calc_bw_and_loss_routingtable(self):
        self._routing_table['formular_bw_loss']=list()
        for dest_id, dest_data in self.fib['bw_and_loss'].items():
            for network in dest_data['networks']:
                bwloss_entry=dict()
                for prefix_type, prefix_ip in network.items():
                    bwloss_entry['proto'] = "v4"
                    ip_pref_len = prefix_ip.split("/")
                    bwloss_entry['prefix'] = ip_pref_len[0]
                    bwloss_entry['prefix-len'] = ip_pref_len[1]
                search_key='{}>{}'.format(self._conf["id"], dest_data['next-hop'])
                for path, path_num in dest_data['paths'].items():
                    if path == search_key:
                       for fib_path, fib_path_data in self.fib['path_characteristics'].items():
                           if fib_path == path_num:
                              path_found = False
                              for iface in self._conf['interfaces']:
                                  path_char = dict()
                                  path_char = iface['link-characteristics']
                                  if path_char['loss']==fib_path_data['loss'] and path_char['bandwidth']==fib_path_data['bandwidth']:
                                     path_found = True
                                     bwloss_entry['interface'] = iface['name']
                                     break
                              if path_found==True:
                                 break
                    break
                bwloss_entry['next-hop'] = self.next_hop_ip_addr(bwloss_entry['proto'], dest_data['next-hop'], bwloss_entry['interface'])
                self._routing_table['formular_bw_loss'].append(bwloss_entry)


    def _calc_cost_routingtable(self):
        self._routing_table['no-cost']=list()
        for dest_id, dest_data in self.fib['no_cost'].items():
            for network in dest_data['networks']:
                cost_entry=dict()
                for prefix_type, prefix_ip in network.items():
                    cost_entry['proto'] = "v4"
                    ip_pref_len = prefix_ip.split("/")
                    cost_entry['prefix'] = ip_pref_len[0]
                    cost_entry['prefix-len'] = ip_pref_len[1]
                search_key='{}>{}'.format(self._conf["id"], dest_data['next-hop'])
                for path, path_num in dest_data['paths'].items():
                    if path == search_key:
                       for fib_path, fib_path_data in self.fib['path_characteristics'].items():
                           if fib_path == path_num:
                              path_found = False
                              for iface in self._conf['interfaces']:
                                  path_char = dict()
                                  path_char = iface['link-characteristics']
                                  if path_char['cost']==fib_path_data['cost']:
                                     path_found = True
                                     cost_entry['interface'] = iface['name']
                                     break
                              if path_found==True:
                                 break
                    break
                cost_entry['next-hop'] = self.next_hop_ip_addr(cost_entry['proto'], dest_data['next-hop'], cost_entry['interface'])
                self._routing_table['no-cost'].append(cost_entry)


    def _calc_bw_and_cost_routingtable(self):
        self._routing_table['filtered-bw-cost']=list()
        for dest_id, dest_data in self.fib['bw_and_cost'].items():
            for network in dest_data['networks']:
                bw_cost_entry=dict()
                for prefix_type, prefix_ip in network.items():
                    bw_cost_entry['proto'] = "v4"
                    ip_pref_len = prefix_ip.split("/")
                    bw_cost_entry['prefix'] = ip_pref_len[0]
                    bw_cost_entry['prefix-len'] = ip_pref_len[1]
                search_key='{}>{}'.format(self._conf["id"], dest_data['next-hop'])
                for path, path_num in dest_data['paths'].items():
                    if path == search_key:
                       for fib_path, fib_path_data in self.fib['path_characteristics'].items():
                           if fib_path == path_num:
                              path_found = False
                              for iface in self._conf['interfaces']:
                                  path_char = dict()
                                  path_char = iface['link-characteristics']
                                  if path_char['cost']==fib_path_data['cost'] and path_char['bandwidth']==fib_path_data['bandwidth']:
                                     path_found = True
                                     bw_cost_entry['interface'] = iface['name']
                                     break
                              if path_found==True:
                                 break
                    break
                bw_cost_entry['next-hop'] = self.next_hop_ip_addr(bw_cost_entry['proto'], dest_data['next-hop'], bw_cost_entry['interface'])
                self._routing_table['filtered-bw-cost'].append(bw_cost_entry)


    def register_get_time_cb(self, function, priv_data=None):
        self._get_time = function
        self._get_time_priv_data = priv_data


    def register_routing_table_update_cb(self, function, priv_data=None):
        self._routing_table_update_func = function
        self._routing_table_update_func_priv_data = priv_data


    def register_msg_tx_cb(self, function, priv_data=None):
        """ when a DMPR packet must be transmitted
        the surrounding framework must register this
        function. The prototype for the function should look like:
        func(interface_name, proto, dst_mcast_addr, packet)
        """
        self._packet_tx_func = function
        self._packet_tx_func_priv_data = priv_data


    def _routing_table_update(self):
        """ return the calculated routing tables in the following form:
             {
             "lowest-loss" : [
                { "proto" : "v4", "prefix" : "10.10.0.0", "prefix-len" : "24", "next-hop" : "192.168.1.1", "interface" : "wifi0" },
                { "proto" : "v4", "prefix" : "10.11.0.0", "prefix-len" : "24", "next-hop" : "192.168.1.2", "interface" : "wifi0" },
                { "proto" : "v4", "prefix" : "10.12.0.0", "prefix-len" : "24", "next-hop" : "192.168.1.1", "interface" : "tetra0" },
             ]
             "highest-bandwidth" : [
                { "proto" : "v4", "prefix" : "10.10.0.0", "prefix-len" : "24", "next-hop" : "192.168.1.1", "interface" : "wifi0" },
                { "proto" : "v4", "prefix" : "10.11.0.0", "prefix-len" : "24", "next-hop" : "192.168.1.2", "interface" : "wifi0" },
                { "proto" : "v4", "prefix" : "10.12.0.0", "prefix-len" : "24", "next-hop" : "192.168.1.1", "interface" : "tetra0" },
             ]
             }
        """
        self._routing_table_update_func(self._routing_table,
                                        priv_data=self._routing_table_update_func_priv_data)


    def _packet_tx(self, msg):
        self._packet_tx_func(msg)

