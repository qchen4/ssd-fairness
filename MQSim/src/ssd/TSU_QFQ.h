#ifndef TSU_QFQ_H
#define TSU_QFQ_H

#include <vector>
#include "TSU_Base.h"
#include "NVM_Transaction_Flash.h"
#include "NVM_PHY_ONFI_NVDDR2.h"
#include "FTL.h"

namespace SSD_Components
{
class FTL;

class TSU_QFQ : public TSU_Base
{
public:
	TSU_QFQ(const sim_object_id_type& id,
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
			sim_time_type EraseReasonableSuspensionTimeForWrite);
	~TSU_QFQ();

	void Schedule();

	void Start_simulation();
	void Validate_simulation_config();
	void Execute_simulator_event(MQSimEngine::Sim_Event* event);
	void Report_results_in_XML(std::string name_prefix, Utils::XmlWriter& xmlwriter);

private:
	struct FlowState
	{
		double weight;
		double service;
		double last_finish_tag;
		FlowState() : weight(1.0), service(0), last_finish_tag(0) {}
	};

	Flash_Transaction_Queue** UserReadTRQueue;
	Flash_Transaction_Queue** UserWriteTRQueue;
	Flash_Transaction_Queue** GCReadTRQueue;
	Flash_Transaction_Queue** GCWriteTRQueue;
	Flash_Transaction_Queue** GCEraseTRQueue;
	Flash_Transaction_Queue** MappingReadTRQueue;
	Flash_Transaction_Queue** MappingWriteTRQueue;

	std::vector<FlowState> flow_state;
	double virtual_time;

	FlowState& get_flow_state(stream_id_type sid);
	NVM_Transaction_Flash* pick_next_user_transaction(Flash_Transaction_Queue& queue);
	void apply_qfq_if_user_queue(Flash_Transaction_Queue* queue, flash_channel_ID_type channel_id, flash_chip_ID_type chip_id);

	bool service_read_transaction(NVM::FlashMemory::Flash_Chip* chip);
	bool service_write_transaction(NVM::FlashMemory::Flash_Chip* chip);
	bool service_erase_transaction(NVM::FlashMemory::Flash_Chip* chip);
};
} // namespace SSD_Components

#endif // TSU_QFQ_H

