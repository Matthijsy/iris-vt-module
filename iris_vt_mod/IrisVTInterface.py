#!/usr/bin/env python3
#
#  IRIS VT Module Source Code
#  contact@dfir-iris.org
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
import logging
from virus_total_apis import PublicApi, PrivateApi

from iris_interface.IrisModuleInterface import IrisPipelineTypes, IrisModuleInterface, IrisModuleTypes
import iris_interface.IrisInterfaceStatus as InterfaceStatus

import iris_vt_mod.IrisVTConfig as interface_conf

log = logging.getLogger(__name__)


class IrisVTInterface(IrisModuleInterface):
    """
    Provide the interface between Iris and VT
    """
    name = "IrisVTInterface"
    _module_name = interface_conf.module_name
    _module_description = interface_conf.module_description
    _interface_version = interface_conf.interface_version
    _module_version = interface_conf.module_version
    _pipeline_support = interface_conf.pipeline_support
    _pipeline_info = interface_conf.pipeline_info
    _module_configuration = interface_conf.module_configuration
    _module_type = IrisModuleTypes.module_processor

    def register_hooks(self, module_id: int):
        """
        Registers all the hooks

        :param module_id: Module ID provided by IRIS
        :return: Nothing
        """
        status = self.register_to_hook(module_id, iris_hook_name='on_postload_ioc_create')
        if status.is_failure():
            log.error(status.get_message())
            log.error(status.get_data())

        else:
            log.info("Successfully registered on_postload_ioc_create hook")

        self.register_to_hook(module_id, iris_hook_name='on_postload_ioc_update')
        if status.is_failure():
            log.error(status.get_message())
            log.error(status.get_data())

        else:
            log.info("Successfully registered on_postload_ioc_update hook")

        self.register_to_hook(module_id, iris_hook_name='on_preload_ioc_update')
        if status.is_failure():
            log.error(status.get_message())
            log.error(status.get_data())

        else:
            log.info("Successfully registered on_preload_ioc_update hook")

        self.register_to_hook(module_id, iris_hook_name='on_manual_trigger_ioc',
                              manual_hook_name="Process with VT module", is_manual_hook=True)

        if status.is_failure():
            log.error(status.get_message())
            log.error(status.get_data())

        else:
            log.info("Successfully registered on_manual_trigger_ioc hook")

    def hooks_handler(self, hook_name: str, data):
        """
        Hooks handler table. Calls corresponding methods depending on the hooks name.

        :param hook_name: Name of the hook which triggered
        :param data: Data associated with the trigger.
        :return: Data
        """
        log.addHandler(self.set_log_handler())

        log.info(f'Received {hook_name}')
        if hook_name == 'on_postload_ioc_create':
            status = self._handle_ioc(data=data)

        elif hook_name == "on_postload_ioc_update":
            status = self._handle_ioc(data=data)

        elif hook_name == "on_preload_ioc_update":
            data['ioc_value'] = "changed"
            status = InterfaceStatus.I2Success

        elif hook_name == "on_manual_trigger_ioc":
            status = self._handle_ioc(data=data)

        else:
            log.critical(f'Received unsupported hook {hook_name}')
            return InterfaceStatus.I2Error(data=data, logs=list(self.message_queue))

        if status.is_failure():
            log.error(f"Encountered error processing hook {hook_name}")
            return InterfaceStatus.I2Error(data=data, logs=list(self.message_queue))

        log.info(f"Successfully processed hook {hook_name}")
        return InterfaceStatus.I2Success(data=data, logs=list(self.message_queue))

    def get_vt_instance(self):
        """
        Returns an VT API instance depending if the key is premium or not

        :return: VT Instance
        """
        is_premium = self._dict_conf .get('vt_key_is_premium')
        api_key = self._dict_conf .get('vt_api_key')

        if is_premium:
            return PrivateApi(api_key)
        else:
            return PublicApi(api_key)

    def _handle_ioc(self, data) -> InterfaceStatus.IIStatus:
        """
        Handle the IOC data the module just received. The module registered
        to on_postload hooks, so it receives instances of IOC object.
        These objects are attached to a dedicated SQlAlchemy session so data can
        be modified safely.

        :param data: Data associated to the hook, here IOC object
        :return: IIStatus
        """

        # Check that the IOC we receive is of type the module can handle and dispatch
        if 'ip-' in data.ioc_type.type_name:
            return self._handle_vt_ip(ioc=data)

        elif 'domain' in data.ioc_type.type_name:
            return self._handle_vt_domain(ioc=data)

        log.error(f'IOC type {data.ioc_type.type_name} not handled by VT module. Skipping')
        return InterfaceStatus.I2Success(data=data)

    def _handle_vt_domain(self, ioc):
        """
        Handles an IOC of type domain and adds VT insights

        :param ioc: IOC instance
        :return: IIStatus
        """
        vt = self.get_vt_instance()

        log.info(f'Getting domain report for {ioc.ioc_value}')
        report = vt.get_domain_report(ioc.ioc_value)

        log.info(f'VT report fetched.')
        results = report.get('results')

        if results.get('response_code') == 0:
            log.error(f'Got invalid feedback from VT :: {results.get("verbose_msg")}')
            return InterfaceStatus.I2Success

        if self._dict_conf.get('vt_domain_add_whois_as_desc') is True:
            ioc.ioc_description = f"{ioc.ioc_description}\n\nWHOIS\n {report.get('results').get('whois')}"

        return InterfaceStatus.I2Success

    def _handle_vt_ip(self, ioc):
        """
        Handles an IOC of type IP and adds VT insights

        :param ioc: IOC instance
        :return: IIStatus
        """
        vt = self.get_vt_instance()

        log.info(f'Getting IP report for {ioc.ioc_value}')
        report = vt.get_ip_report(ioc.ioc_value)

        log.info(f'VT report fetched.')

        results = report.get('results')

        if results.get('response_code') == 0:
            log.error(f'Got invalid feedback from VT :: {results.get("verbose_msg")}')
            return InterfaceStatus.I2Success

        if self._dict_conf.get('vt_ip_assign_asn_as_tag') is True:
            log.info('Assigning new ASN tag to IOC.')

            asn = report.get('results').get('asn')
            if asn is None:
                log.info('ASN was nul - skipping')

            ioc.ioc_tags = f"{ioc.ioc_tags},ASN:{report.get('results').get('asn')}"

        return InterfaceStatus.I2Success
