#include "CompositionLaneComponent.h"

#include "V2Chrome.h"

namespace acestep::vst3
{
CompositionLaneComponent::CompositionLaneComponent()
{
    for (auto* label : {&projectNameLabel_, &sectionPlanLabel_, &chordProgressionLabel_,
                        &exportNotesLabel_, &exportStatusLabel_})
    {
        label->setColour(juce::Label::textColourId, v2::kLabelMuted);
        label->setJustificationType(juce::Justification::centredLeft);
        addAndMakeVisible(*label);
    }

    projectNameLabel_.setText("Project Name", juce::dontSendNotification);
    sectionPlanLabel_.setText("Section Plan", juce::dontSendNotification);
    chordProgressionLabel_.setText("Chord Progression", juce::dontSendNotification);
    exportNotesLabel_.setText("Export Notes", juce::dontSendNotification);
    exportStatusLabel_.setText("No session export written yet.", juce::dontSendNotification);
    exportStatusLabel_.setColour(juce::Label::textColourId, v2::kAccentMint);

    sectionPlanEditor_.setMultiLine(true);
    chordProgressionEditor_.setMultiLine(true);
    exportNotesEditor_.setMultiLine(true);

    for (auto* component : {static_cast<juce::Component*>(&projectNameEditor_),
                            static_cast<juce::Component*>(&sectionPlanEditor_),
                            static_cast<juce::Component*>(&chordProgressionEditor_),
                            static_cast<juce::Component*>(&exportNotesEditor_),
                            static_cast<juce::Component*>(&exportButton_)})
    {
        addAndMakeVisible(*component);
    }
}

void CompositionLaneComponent::paint(juce::Graphics& g)
{
    v2::drawModule(g, getLocalBounds(), "Composition Lane", v2::kAccentAmber);
}

void CompositionLaneComponent::resized()
{
    auto area = getLocalBounds().reduced(18);
    area.removeFromTop(24);

    auto left = area.removeFromLeft(area.getWidth() / 2);
    auto right = area;
    const auto labelHeight = 18;
    const auto fieldHeight = 32;

    projectNameLabel_.setBounds(left.removeFromTop(labelHeight));
    projectNameEditor_.setBounds(left.removeFromTop(fieldHeight));
    left.removeFromTop(10);
    sectionPlanLabel_.setBounds(left.removeFromTop(labelHeight));
    sectionPlanEditor_.setBounds(left.removeFromTop(84));
    left.removeFromTop(10);
    chordProgressionLabel_.setBounds(left.removeFromTop(labelHeight));
    chordProgressionEditor_.setBounds(left.removeFromTop(54));

    exportNotesLabel_.setBounds(right.removeFromTop(labelHeight));
    exportNotesEditor_.setBounds(right.removeFromTop(138));
    right.removeFromTop(10);
    exportStatusLabel_.setBounds(right.removeFromTop(28));
    right.removeFromTop(12);
    exportButton_.setBounds(right.removeFromTop(34).removeFromLeft(160));
}

juce::TextEditor& CompositionLaneComponent::projectNameEditor() noexcept
{
    return projectNameEditor_;
}

juce::TextEditor& CompositionLaneComponent::sectionPlanEditor() noexcept
{
    return sectionPlanEditor_;
}

juce::TextEditor& CompositionLaneComponent::chordProgressionEditor() noexcept
{
    return chordProgressionEditor_;
}

juce::TextEditor& CompositionLaneComponent::exportNotesEditor() noexcept
{
    return exportNotesEditor_;
}

juce::TextButton& CompositionLaneComponent::exportButton() noexcept { return exportButton_; }

void CompositionLaneComponent::setExportStatus(const juce::String& status)
{
    exportStatusLabel_.setText(status, juce::dontSendNotification);
}
}  // namespace acestep::vst3
