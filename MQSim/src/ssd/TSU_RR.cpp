#include "TSU_RR.h"
#include <algorithm>
#include <limits>

namespace SSD_Components
{

TSU_RR::TSU_RR(const sim_object_id_type& id,
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
	: TSU_Base(id, ftl, NVMController, Flash_Scheduling_Type::RR, ChannelCount, chip_no_per_channel, DieNoPerChip, PlaneNoPerDie,
			   EraseSuspensionEnabled, ProgramSuspensionEnabled,
			   WriteReasonableSuspensionTimeForRead, EraseReasonableSuspensionTimeForRead, EraseReasonableSuspensionTimeForWrite)
{
	UserReadTRQueue = new Flash_Transaction_Queue*[channel_count];
	UserWriteTRQueue = new Flash_Transaction_Queue*[channel_count];
	GCReadTRQueue = new Flash_Transaction_Queue*[channel_count];
	GCWriteTRQueue = new Flash_Transaction_Queue*[channel_count];
	GCEraseTRQueue = new Flash_Transaction_Queue*[channel_count];
	MappingReadTRQueue = new Flash_Transaction_Queue*[channel_count];
	MappingWriteTRQueue = new Flash_Transaction_Queue*[channel_count];

	current_stream_read = new unsigned int*[channel_count];
	current_stream_write = new unsigned int*[channel_count];

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		UserReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		UserWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		GCReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		GCWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		GCEraseTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		MappingReadTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];
		MappingWriteTRQueue[channelID] = new Flash_Transaction_Queue[chip_no_per_channel];

		current_stream_read[channelID] = new unsigned int[chip_no_per_channel];
		current_stream_write[channelID] = new unsigned int[chip_no_per_channel];

		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			UserReadTRQueue[channelID][chip_cntr].Set_id("RR_User_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			UserWriteTRQueue[channelID][chip_cntr].Set_id("RR_User_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			GCReadTRQueue[channelID][chip_cntr].Set_id("RR_GC_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			GCWriteTRQueue[channelID][chip_cntr].Set_id("RR_GC_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			GCEraseTRQueue[channelID][chip_cntr].Set_id("RR_GC_Erase_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			MappingReadTRQueue[channelID][chip_cntr].Set_id("RR_Mapping_Read_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));
			MappingWriteTRQueue[channelID][chip_cntr].Set_id("RR_Mapping_Write_TR_Queue@" + std::to_string(channelID) + "@" + std::to_string(chip_cntr));

			current_stream_read[channelID][chip_cntr] = 0;
			current_stream_write[channelID][chip_cntr] = 0;
		}
	}
}

TSU_RR::~TSU_RR()
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
		delete[] current_stream_read[channelID];
		delete[] current_stream_write[channelID];
	}
	delete[] UserReadTRQueue;
	delete[] UserWriteTRQueue;
	delete[] GCReadTRQueue;
	delete[] GCWriteTRQueue;
	delete[] GCEraseTRQueue;
	delete[] MappingReadTRQueue;
	delete[] MappingWriteTRQueue;
	delete[] current_stream_read;
	delete[] current_stream_write;
}

void TSU_RR::Start_simulation()
{
}

void TSU_RR::Validate_simulation_config()
{
}

void TSU_RR::Execute_simulator_event(MQSimEngine::Sim_Event* event)
{
}

void TSU_RR::Schedule()
{
	opened_scheduling_reqs--;
	if (opened_scheduling_reqs > 0)
		return;
	if (opened_scheduling_reqs < 0)
		PRINT_ERROR("TSU_RR: Illegal status!");
	if (transaction_receive_slots.size() == 0)
		return;

	// Distribute transactions to appropriate queues
	for (auto it = transaction_receive_slots.begin(); it != transaction_receive_slots.end(); it++)
	{
		switch ((*it)->Type)
		{
		case Transaction_Type::READ:
			switch ((*it)->Source)
			{
			case Transaction_Source_Type::CACHE:
			case Transaction_Source_Type::USERIO:
				UserReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			case Transaction_Source_Type::MAPPING:
				MappingReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			case Transaction_Source_Type::GC_WL:
				GCReadTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			default:
				PRINT_ERROR("TSU_RR: unknown source type for a read transaction!")
			}
			break;
		case Transaction_Type::WRITE:
			switch ((*it)->Source)
			{
			case Transaction_Source_Type::CACHE:
			case Transaction_Source_Type::USERIO:
				UserWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			case Transaction_Source_Type::MAPPING:
				MappingWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			case Transaction_Source_Type::GC_WL:
				GCWriteTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
				break;
			default:
				PRINT_ERROR("TSU_RR: unknown source type for a write transaction!")
			}
			break;
		case Transaction_Type::ERASE:
			GCEraseTRQueue[(*it)->Address.ChannelID][(*it)->Address.ChipID].push_back(*it);
			break;
		default:
			break;
		}
	}

	// Process each channel
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

NVM_Transaction_Flash* TSU_RR::pick_next_rr_transaction(Flash_Transaction_Queue& queue, unsigned int& current_stream)
{
	if (queue.size() == 0)
		return NULL;

	// Collect all unique stream IDs in the queue
	std::vector<stream_id_type> stream_ids;
	for (auto it = queue.begin(); it != queue.end(); ++it)
	{
		stream_id_type sid = (*it)->Stream_id;
		if (std::find(stream_ids.begin(), stream_ids.end(), sid) == stream_ids.end())
		{
			stream_ids.push_back(sid);
		}
	}

	if (stream_ids.empty())
		return NULL;

	// Ensure current_stream is valid
	if (current_stream >= stream_ids.size())
		current_stream = 0;

	// Find next transaction from current stream (round-robin)
	for (unsigned int attempt = 0; attempt < stream_ids.size(); attempt++)
	{
		stream_id_type target_sid = stream_ids[current_stream];
		
		// Find first transaction with this stream ID
		for (auto it = queue.begin(); it != queue.end(); ++it)
		{
			if ((*it)->Stream_id == target_sid)
			{
				NVM_Transaction_Flash* chosen = *it;
				queue.remove(it);
				queue.push_front(chosen);
				
				// Move to next stream for next time
				current_stream = (current_stream + 1) % stream_ids.size();
				return chosen;
			}
		}
		
		// Stream not found, try next
		current_stream = (current_stream + 1) % stream_ids.size();
	}

	return NULL;
}

bool TSU_RR::service_read_transaction(NVM::FlashMemory::Flash_Chip* chip)
{
	Flash_Transaction_Queue* sourceQueue1 = NULL, *sourceQueue2 = NULL;

	// Mapping reads have highest priority
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
		else if (GCWriteTRQueue[chip->ChannelID][chip->ChipID].size() > 0 || GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() > 0)
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
		break;
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
		break;
	default:
		return false;
	}

	// Apply round-robin to user queues
	if (sourceQueue1 == &UserReadTRQueue[chip->ChannelID][chip->ChipID])
	{
		pick_next_rr_transaction(*sourceQueue1, current_stream_read[chip->ChannelID][chip->ChipID]);
	}
	if (sourceQueue2 == &UserReadTRQueue[chip->ChannelID][chip->ChipID])
	{
		pick_next_rr_transaction(*sourceQueue2, current_stream_read[chip->ChannelID][chip->ChipID]);
	}

	issue_command_to_chip(sourceQueue1, sourceQueue2, Transaction_Type::READ, suspensionRequired);
	return true;
}

bool TSU_RR::service_write_transaction(NVM::FlashMemory::Flash_Chip* chip)
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
		{
			return false;
		}
		if (_NVMController->Expected_finish_time(chip) - Simulator->Time() < eraseReasonableSuspensionTimeForWrite)
		{
			return false;
		}
		suspensionRequired = true;
		break;
	default:
		return false;
	}

	// Apply round-robin to user queues
	if (sourceQueue1 == &UserWriteTRQueue[chip->ChannelID][chip->ChipID])
	{
		pick_next_rr_transaction(*sourceQueue1, current_stream_write[chip->ChannelID][chip->ChipID]);
	}
	if (sourceQueue2 == &UserWriteTRQueue[chip->ChannelID][chip->ChipID])
	{
		pick_next_rr_transaction(*sourceQueue2, current_stream_write[chip->ChannelID][chip->ChipID]);
	}

	issue_command_to_chip(sourceQueue1, sourceQueue2, Transaction_Type::WRITE, suspensionRequired);
	return true;
}

bool TSU_RR::service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip)
{
	if (GCEraseTRQueue[chip->ChannelID][chip->ChipID].size() == 0)
		return false;

	Flash_Transaction_Queue* sourceQueue = &GCEraseTRQueue[chip->ChannelID][chip->ChipID];
	issue_command_to_chip(sourceQueue, NULL, Transaction_Type::ERASE, false);
	return true;
}

void TSU_RR::Report_results_in_XML(std::string name_prefix, Utils::XmlWriter& xmlwriter)
{
	name_prefix = name_prefix + ".TSU_RR";
	xmlwriter.Write_open_tag(name_prefix);

	TSU_Base::Report_results_in_XML(name_prefix, xmlwriter);

	for (unsigned int channelID = 0; channelID < channel_count; channelID++)
	{
		for (unsigned int chip_cntr = 0; chip_cntr < chip_no_per_channel; chip_cntr++)
		{
			UserReadTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".User_Read_TR_Queue", xmlwriter);
			UserWriteTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".User_Write_TR_Queue", xmlwriter);
			GCReadTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".GC_Read_TR_Queue", xmlwriter);
			GCWriteTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".GC_Write_TR_Queue", xmlwriter);
			GCEraseTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".GC_Erase_TR_Queue", xmlwriter);
			MappingReadTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".Mapping_Read_TR_Queue", xmlwriter);
			MappingWriteTRQueue[channelID][chip_cntr].Report_results_in_XML(name_prefix + ".Mapping_Write_TR_Queue", xmlwriter);
		}
	}

	xmlwriter.Write_close_tag();
}

} // namespace SSD_Components

