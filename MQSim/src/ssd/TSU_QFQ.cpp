#include <algorithm>
#include <limits>
#include "TSU_QFQ.h"

namespace SSD_Components
{

TSU_QFQ::TSU_QFQ(const sim_object_id_type& id,
				 FTL* ftl,
				 NVM_PHY_ONFI_NVDDR2* NVMController,
				 unsigned int ChannelCount,
				 unsigned int chip_no_per_channel,
				 unsigned int DieNoPerChip,
				 unsigned int PlaneNoPerDie,
				 bool EraseSuspensionEnabled,
				 bool ProgramSuspensionEnabled,
				 sim_time_type WriteReasonableSuspensionTimeForRead,
				 sim_time_type EraseReasonableSuspensionTimeForRead,
				 sim_time_type EraseReasonableSuspensionTimeForWrite)
	: TSU_Base(id, ftl, NVMController, Flash_Scheduling_Type::QFQ, ChannelCount, chip_no_per_channel, DieNoPerChip, PlaneNoPerDie,
			   EraseSuspensionEnabled, ProgramSuspensionEnabled,
			   WriteReasonableSuspensionTimeForRead, EraseReasonableSuspensionTimeForRead, EraseReasonableSuspensionTimeForWrite),
	  virtual_time(0)
{
	UserReadTRQueue = new Flash_Transaction_Queue *[channel_count];
	UserWriteTRQueue = new Flash_Transaction_Queue *[channel_count];
	GCReadTRQueue = new Flash_Transaction_Queue *[channel_count];
	GCWriteTRQueue = new Flash_Transaction_Queue *[channel_count];
	GCEraseTRQueue = new Flash_Transaction_Queue *[channel_count];
	MappingReadTRQueue = new Flash_Transaction_Queue *[channel_count];
	MappingWriteTRQueue = new Flash_Transaction_Queue *[channel_count];

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		UserReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		UserWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		GCReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		GCWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		GCEraseTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		MappingReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		MappingWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];

		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			UserReadTRQueue[channelID][chip_cntr].Set_id("User_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			UserWriteTRQueue[channelID][chip_cntr].Set_id("User_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			GCReadTRQueue[channelID][chip_cntr].Set_id("GC_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			MappingReadTRQueue[channelID][chip_cntr].Set_id("Mapping_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			MappingWriteTRQueue[channelID][chip_cntr].Set_id("Mapping_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			GCWriteTRQueue[channelID][chip_cntr].Set_id("GC_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			GCEraseTRQueue[channelID][chip_cntr].Set_id("GC_Erase_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
		}
	}
}

TSU_QFQ::~TSU_QFQ()
{
	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		delete[] UserReadTRQueue[channelID];
		delete[] UserWriteTRQueue[channelID];
		delete[] GCReadTRQueue[channelID];
		delete[] GCWriteTRQueue[channelID];
		delete[] GCEraseTRQueue[channelID];
		delete[] MappingReadTRQueue[channelID];
		delete[] MappingWriteTRQueue[channelID];
	}
	delete[] UserReadTRQueue;
	delete[] UserWriteTRQueue;
	delete[] GCReadTRQueue;
	delete[] GCWriteTRQueue;
	delete[] GCEraseTRQueue;
	delete[] MappingReadTRQueue;
	delete[] MappingWriteTRQueue;
}

void TSU_QFQ::Start_simulation()
{
}

void TSU_QFQ::Validate_simulation_config()
{
}

void TSU_QFQ::Execute_simulator_event(MQSimEngine::Sim_Event* event)
{
}

void TSU_QFQ::Report_results_in_XML(std::string name_prefix, Utils::XmlWriter& xmlwriter)
{
	name_prefix = name_prefix + ".TSU_QFQ";
	xmlwriter.Write_open_tag(name_prefix);

	TSU_Base::Report_results_in_XML(name_prefix, xmlwriter);

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			UserReadTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".User_Read_TR_Queue", xmlwriter);
		}
	}

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			UserWriteTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".User_Write_TR_Queue", xmlwriter);
		}
	}

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			MappingReadTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".Mapping_Read_TR_Queue", xmlwriter);
		}
	}

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			MappingWriteTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".Mapping_Write_TR_Queue", xmlwriter);
		}
	}

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			GCReadTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".GC_Read_TR_Queue", xmlwriter);
		}
	}

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			GCWriteTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".GC_Write_TR_Queue", xmlwriter);
		}
	}

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			GCEraseTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".GC_Erase_TR_Queue", xmlwriter);
		}
	}

	xmlwriter.Write_close_tag();
}

void TSU_QFQ::Schedule()
{
	opened_scheduling_reqs--;
	if (opened_scheduling_reqs > 0)
	{
		return;
	}

	if (opened_scheduling_reqs < 0)
	{
		PRINT_ERROR("TSU_QFQ: Illegal status!");
	}

	if (transaction_receive_slots.size() == 0)
	{
		return;
	}

	for (std::list<NVM_Transaction_Flash*>::iterator it = transaction_receive_slots.begin(); it != transaction_receive_slots.end(); it++)
	{
		switch ((*it)->Type)
		{
		case Transaction_Type::READ:
			switch ((*it)->Source)
			{
			case Transaction_Source_Type::CACHE:
			case Transaction_Source_Type::USERIO:
				UserReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
				break;
			case Transaction_Source_Type::MAPPING:
				MappingReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
				break;
			case Transaction_Source_Type::GC_WL:
				GCReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
				break;
			default:
				PRINT_ERROR("TSU_QFQ: unknown source type for a read transaction!")
			}
			break;
		case Transaction_Type::WRITE:
			switch ((*it)->Source)
			{
			case Transaction_Source_Type::CACHE:
			case Transaction_Source_Type::USERIO:
				UserWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
				break;
			case Transaction_Source_Type::MAPPING:
				MappingWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
				break;
			case Transaction_Source_Type::GC_WL:
				GCWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
				break;
			default:
				PRINT_ERROR("TSU_QFQ: unknown source type for a write transaction!")
			}
			break;
		case Transaction_Type::ERASE:
			GCEraseTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back((*it));
			break;
		default:
			break;
		}
	}

	for (flash_channel_ID_type channelID = 0; channelID < channel_count; channelID++)
	{
		if (_NVMController->Get_channel_status(channelID) == BusChannelStatus::IDLE)
		{
			for (unsigned int i = 0; i < chip_no_per_channel; i++)
			{
				NVM::FlashMemory::Flash_Chip* chip = _NVMController->Get_chip(channelID, Round_robin_turn_of_channel[channelID]);
				process_chip_requests(chip);
				Round_robin_turn_of_channel[channelID] = (flash_chip_ID_type)(Round_robin_turn_of_channel[channelID] + 1) % chip_no_per_channel;
				if (_NVMController->Get_channel_status(chip->ChannelID) != BusChannelStatus::IDLE)
				{
					break;
				}
			}
		}
	}
}

TSU_QFQ::FlowState& TSU_QFQ::get_flow_state(stream_id_type sid)
{
	if (sid >= flow_state.size())
	{
		flow_state.resize(sid + 1);
	}
	return flow_state[sid];
}

NVM_Transaction_Flash* TSU_QFQ::pick_next_user_transaction(Flash_Transaction_Queue& queue)
{
	if (queue.size() == 0)
	{
		return NULL;
	}

	auto best_it = queue.begin();
	double best_finish_tag = std::numeric_limits<double>::max();
	NVM_Transaction_Flash* chosen = NULL;

	for (auto it = queue.begin(); it != queue.end(); ++it)
	{
		NVM_Transaction_Flash* tr = *it;
		stream_id_type sid = tr->Stream_id;
		FlowState& fs = get_flow_state(sid);
		const double size_units = 1.0; // TODO: Use actual request size
		double start = std::max(virtual_time, fs.last_finish_tag);
		double finish_tag = start + size_units / fs.weight;
		if (finish_tag < best_finish_tag)
		{
			best_finish_tag = finish_tag;
			best_it = it;
			chosen = tr;
		}
	}

	if (chosen == NULL)
	{
		return NULL;
	}

	queue.splice(queue.begin(), queue, best_it);

	FlowState& fs = get_flow_state(chosen->Stream_id);
	const double size_units = 1.0;
	double start = std::max(virtual_time, fs.last_finish_tag);
	double finish_tag = start + size_units / fs.weight;
	fs.last_finish_tag = finish_tag;
	fs.service += size_units;
	virtual_time = std::max(virtual_time, finish_tag);

	return chosen;
}

void TSU_QFQ::apply_qfq_if_user_queue(Flash_Transaction_Queue* queue, flash_channel_ID_type channel_id, flash_chip_ID_type chip_id)
{
	if (queue == NULL || queue->size() == 0)
	{
		return;
	}

	Flash_Transaction_Queue* user_read_queue = &UserReadTRQueue[channel_id][chip_id];
	Flash_Transaction_Queue* user_write_queue = &UserWriteTRQueue[channel_id][chip_id];

	if (queue == user_read_queue || queue == user_write_queue)
	{
		pick_next_user_transaction(*queue);
	}
}

bool TSU_QFQ::service_read_transaction(NVM::FlashMemory::Flash_Chip* chip)
{
	Flash_Transaction_Queue* sourceQueue1 = NULL, *sourceQueue2 = NULL;

	if (MappingReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
	{
		sourceQueue1 = &MappingReadTRQueue[chip->ChannelID][chip->ChipID];
		if (ftl->GC_and_WL_Unit->GC_is_in_urgent_mode(chip) && GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue2 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
		}
		else if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue2 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
		}
	}
	else if (ftl->GC_and_WL_Unit->GC_is_in_urgent_mode(chip))
	{
		if (GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
			if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue2 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
			}
		}
		else if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			return false;
		}
		else if (GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			return false;
		}
		else if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
		}
		else
		{
			return false;
		}
	}
	else
	{
		if (UserReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &UserReadTRQueue[chip->ChannelID][chip->ChipID];
			if (GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue2 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
			}
		}
		else if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			return false;
		}
		else if (GCReadTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &GCReadTRQueue[chip->ChannelID][chip->ChipID];
		}
		else
		{
			return false;
		}
	}

	bool suspensionRequired = false;
	ChipStatus cs = _NVMController->GetChipStatus(chip);
	switch (cs)
	{
	case ChipStatus::IDLE:
		break;
	case ChipStatus::WRITING:
		if (!programSuspensionEnabled || _NVMController->HasSuspendedCommand(chip))
		{
			return false;
		}
		if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < writeReasonableSuspensionTimeForRead)
		{
			return false;
		}
		suspensionRequired = true;
	case ChipStatus::ERASING:
		if (!eraseSuspensionEnabled || _NVMController->HasSuspendedCommand(chip))
		{
			return false;
		}
		if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < eraseReasonableSuspensionTimeForRead)
		{
			return false;
		}
		suspensionRequired = true;
	default:
		return false;
	}

	apply_qfq_if_user_queue(sourceQueue1, chip->ChannelID, chip->ChipID);
	apply_qfq_if_user_queue(sourceQueue2, chip->ChannelID, chip->ChipID);

	issue_command_to_chip(sourceQueue1, sourceQueue2, Transaction_Type::READ, suspensionRequired);

	return true;
}

bool TSU_QFQ::service_write_transaction(NVM::FlashMemory::Flash_Chip* chip)
{
	Flash_Transaction_Queue* sourceQueue1 = NULL, *sourceQueue2 = NULL;

	if (ftl->GC_and_WL_Unit->GC_is_in_urgent_mode(chip))
	{
		if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &GCWriteTRQueue[chip->ChannelID][chip->ChipID];
			if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue2 = &UserWriteTRQueue[chip->ChannelID][chip->ChipID];
			}
		}
		else if (GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			return false;
		}
		else if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &UserWriteTRQueue[chip->ChannelID][chip->ChipID];
		}
		else
		{
			return false;
		}
	}
	else
	{
		if (UserWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &UserWriteTRQueue[chip->ChannelID][chip->ChipID];
			if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
			{
				sourceQueue2 = &GCWriteTRQueue[chip->ChannelID][chip->ChipID];
			}
		}
		else if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
		{
			sourceQueue1 = &GCWriteTRQueue[chip->ChannelID][chip->ChipID];
		}
		else
		{
			return false;
		}
	}

	bool suspensionRequired = false;
	ChipStatus cs = _NVMController->GetChipStatus(chip);
	switch (cs)
	{
	case ChipStatus::IDLE:
		break;
	case ChipStatus::ERASING:
		if (!eraseSuspensionEnabled || _NVMController->HasSuspendedCommand(chip))
			return false;
		if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < eraseReasonableSuspensionTimeForWrite)
			return false;
		suspensionRequired = true;
	default:
		return false;
	}

	apply_qfq_if_user_queue(sourceQueue1, chip->ChannelID, chip->ChipID);
	apply_qfq_if_user_queue(sourceQueue2, chip->ChannelID, chip->ChipID);

	issue_command_to_chip(sourceQueue1, sourceQueue2, Transaction_Type::WRITE, suspensionRequired);

	return true;
}

bool TSU_QFQ::service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip)
{
	if (_NVMController->GetChipStatus(chip) != ChipStatus::IDLE)
	{
		return false;
	}

	Flash_Transaction_Queue* source_queue = &GCEraseTRQueue[chip->ChannelID][chip->ChipID];
	if (source_queue->size() == 0)
	{
		return false;
	}

	issue_command_to_chip(source_queue, NULL, Transaction_Type::ERASE, false);

	return true;
}

} // namespace SSD_Components

